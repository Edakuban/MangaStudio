from io import BytesIO
import json
from types import SimpleNamespace
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker, image_signature
from mangastudio.character_render import analysis_graph, generate_character_render
from mangastudio.models import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data', start_worker=False)) as client:
        yield client


def picture():
    stream = BytesIO()
    Image.new('RGB', (160, 240), '#87909a').save(stream, 'PNG')
    return stream.getvalue()


def character(client):
    project = client.post('/api/demo').json()
    result = client.post('/api/projects/'+project['id']+'/characters',
                         data={'name': 'Eira', 'description': 'Adult character with short silver hair.'},
                         files={'file': ('reference.png', picture(), 'image/png')})
    assert result.status_code == 200
    return project, result.json()


def test_vision_graph_uses_separate_model_and_image():
    graph = analysis_graph(Settings(), 'MangaStudio/source.png', 'Eira', 'Silver hair')
    assert graph['1']['inputs']['clip_name'] == Settings().vision_model
    assert graph['2']['inputs']['image'] == ['5', 0]
    assert graph['4']['inputs']['image'] == 'MangaStudio/source.png'


def test_render_pipeline_stages_draft_then_explicit_accept(client, monkeypatch):
    project, char = character(client)
    store = client.app.state.store
    panel = {'characters': [char['id']], 'visual_prompt': 'Character walking', 'shot': 'medium'}
    before = image_signature(project, panel, [char], store.settings())
    res = client.post(f'/api/projects/{project["id"]}/characters/{char["id"]}/render',
                      files={'file': ('render.png', picture(), 'image/png')})
    assert res.status_code == 200, res.text
    job_id = res.json()['job_id']
    assert store.get('characters', char['id'])['image'] == char['image']
    assert image_signature(project, panel, [store.get('characters', char['id'])], store.settings()) == before
    calls = []
    class Client:
        def __init__(self, *args):
            pass
        def upload_input(self, path, **kwargs):
            assert path.is_file()
            calls.append('upload')
            return 'MangaStudio/character-renders/render.png'
        def run_workflow(self, graph, **kwargs):
            kwargs['progress']('vision' if graph.get('2', {}).get('class_type') == 'TextGenerate' else 'image')
            if graph.get('2', {}).get('class_type') == 'TextGenerate':
                calls.append('analysis')
                return SimpleNamespace(ok=True, text_outputs=[json.dumps({'description': 'A fictional adult character with short silver hair and a dark coat.',
                    'observations': 'Kurzes silbernes Haar und ein dunkler Mantel sind sichtbar.', 'uncertainty': 'Augenfarbe nicht eindeutig.'})])
            calls.append('image')
            assert sum(node['class_type']=='ReferenceLatent' for node in graph.values()) == 2
            return SimpleNamespace(ok=True, output_files=['MangaStudio/draft.png'])
        def download_output(self, name, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(picture())
    monkeypatch.setattr('mangastudio.character_render.ComfyClient', Client)
    job = store.job(job_id)
    generate_character_render(Worker(store), job)
    saved = store.get('characters', char['id'])
    assert calls == ['upload', 'analysis', 'image']
    assert saved['image'] == char['image']
    assert saved['description'] == char['description']
    assert store.asset(saved['manga_draft']['image']).is_file()
    assert image_signature(project, panel, [saved], store.settings()) == before
    # A restart after saving a completed result must not submit another generation.
    generate_character_render(Worker(store), store.job(job_id))
    assert calls == ['upload', 'analysis', 'image']
    store.update_job(job_id, state='done')
    endpoint = f'/api/projects/{project["id"]}/characters/{char["id"]}/render/accept'
    assert client.post(endpoint, json={'image': 'books/stale.png'}).status_code == 409
    res = client.post(endpoint, json={'image': saved['manga_draft']['image']})
    assert res.status_code == 200, res.text
    assert res.json()['image'] == saved['manga_draft']['image']
    assert res.json()['description'] == char['description']
    assert image_signature(project, panel, [res.json()], store.settings()) != before
    res = client.post(endpoint, json={'image': saved['manga_draft']['image'], 'use_description': True})
    assert res.json()['description'] == saved['manga_draft']['analysis']['description']


def test_new_character_can_queue_render_without_active_reference(client):
    project = client.post('/api/demo').json()
    res = client.post(f'/api/projects/{project["id"]}/characters',
                      data={'name': 'Eira', 'description': 'Adult character with silver hair.'},
                      files={'render_file': ('render.png', picture(), 'image/png')})
    assert res.status_code == 200, res.text
    assert res.json()['image'] == ''
    job = client.app.state.store.job(res.json()['job_id'])
    assert job['kind'] == 'character_render' and job['chapter_id'] is None
    assert job['payload']['source_image'] == res.json()['render_source']


def test_render_respects_book_ownership_and_busy_guard(client):
    project, char = character(client)
    other = client.post('/api/import', files={'file': ('another.txt', b'A different story begins.')}).json()
    endpoint = f'/api/projects/{other["id"]}/characters/{char["id"]}/render'
    assert client.post(endpoint, files={'file': ('bad.png', picture())}).status_code == 404
    endpoint = f'/api/projects/{project["id"]}/characters/{char["id"]}/render'
    assert client.post(endpoint, files={'file': ('bad.png', b'not an image')}).status_code == 400
    assert client.post(endpoint, files={'file': ('render.png', picture())}).status_code == 200
    assert client.post(endpoint, files={'file': ('render.png', picture())}).status_code == 409


def test_retry_skips_completed_analysis(client, monkeypatch):
    project, char = character(client)
    store = client.app.state.store
    response = client.post(f'/api/projects/{project["id"]}/characters/{char["id"]}/render', files={'file': ('source.png', picture())}).json()
    ident = response['job_id']
    payload = store.job(ident)['payload']
    payload.update(uploaded_source='cached.png', analysis={'description': 'A character with silver hair, a dark coat and a clear silhouette.',
                    'observations': 'Ein Charakter mit silbernem Haar und einem dunklen Mantel.', 'uncertainty': ''},
                    remote={'operation':'character-manga:'+char['id'], 'prompt_id':'known-image'})
    store.update_job(ident, payload=payload)
    class Client:
        def __init__(self, *args):
            pass
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'known-image'
            return SimpleNamespace(ok=True, output_files=['draft.png'])
        def run_workflow(self, *args, **kwargs):
            raise AssertionError('Should resume existing image, not rerun analysis or generation')
        def download_output(self, filename, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(picture())
    monkeypatch.setattr('mangastudio.character_render.ComfyClient', Client)
    generate_character_render(Worker(store), store.job(ident))
    assert store.get('characters', char['id'])['manga_draft']['analysis'] == payload['analysis']
