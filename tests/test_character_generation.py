from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker
from mangastudio.character_generation import generate_character_image


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data', start_worker=False)) as client:
        project = client.post('/api/demo').json()
        char = client.post(f'/api/projects/{project["id"]}/characters', data={
            'name': 'Eira', 'description': 'Adult archivist, silver bob haircut, round glasses, dark long coat.'}).json()
        yield client, project, char


def test_generate_ownership_busy_and_immutable_snapshot(setup):
    client, project, char = setup
    other = client.post('/api/import', files={'file': ('another.txt', b'Another book.')}).json()
    assert client.post(f'/api/projects/{other["id"]}/characters/{char["id"]}/generate').status_code == 404
    endpoint = f'/api/projects/{project["id"]}/characters/{char["id"]}/generate'
    result = client.post(endpoint)
    assert result.status_code == 200
    job = client.app.state.store.job(result.json()['job_id'])
    assert job['kind'] == 'character_generate' and job['chapter_id'] is None
    assert job['payload']['description'] == char['description']
    assert job['payload']['name'] == char['name']
    assert client.post(endpoint).status_code == 409


def test_description_draft_has_no_reference_or_analysis_and_requires_acceptance(setup, monkeypatch):
    client, project, char = setup
    store = client.app.state.store
    char['image'] = 'existing.png'
    char['render_source'] = 'previous-source.png'
    store.write('characters', char, project['id'])
    jobid = client.post(f'/api/projects/{project["id"]}/characters/{char["id"]}/generate').json()['job_id']
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph)
            kwargs['progress']('description-image')
            assert not any(n['class_type'] in ('ReferenceLatent', 'LoadImage', 'TextGenerate') for n in graph.values())
            assert char['description'] in graph['4']['inputs']['text']
            prompt = graph['4']['inputs']['text']
            assert 'completely plain pure white background' in prompt
            assert 'No scenery, room, architecture' in prompt
            assert prompt.index('CHARACTER REFERENCE COMPOSITION') > prompt.index(char['description'])
            return SimpleNamespace(ok=True, output_files=['character.png'])
        def download_output(self, filename, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (128, 128), 'gray').save(path)
    monkeypatch.setattr('mangastudio.character_generation.ComfyClient', Client)
    generate_character_image(Worker(store), store.job(jobid))
    # Checkpoint before job metadata was saved: draft itself prevents re-generation.
    payload = store.job(jobid)['payload']
    payload.pop('completed_image')
    store.update_job(jobid, payload=payload)
    generate_character_image(Worker(store), store.job(jobid))
    assert len(calls) == 1
    saved = store.get('characters', char['id'])
    assert saved['image'] == char['image'] and saved['description'] == char['description']
    assert saved['render_source'] == char['render_source']
    assert saved['manga_draft']['origin'] == 'description' and 'analysis' not in saved['manga_draft']
    store.update_job(jobid, state='done')
    endpoint = f'/api/projects/{project["id"]}/characters/{char["id"]}/render/accept'
    draft = saved['manga_draft']['image']
    assert client.post(endpoint, json={'image': draft, 'use_description': True}).status_code == 400
    assert store.get('characters', char['id'])['image'] == char['image']
    accepted = client.post(endpoint, json={'image': draft, 'use_description': False})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['image'] == draft and accepted.json()['description'] == char['description']


def test_description_generation_resumes_known_remote_prompt(setup, monkeypatch):
    client, project, char = setup
    store = client.app.state.store
    jobid = client.post(f'/api/projects/{project["id"]}/characters/{char["id"]}/generate').json()['job_id']
    payload = store.job(jobid)['payload']
    payload['remote'] = {'operation': 'character-description:'+char['id'], 'prompt_id': 'known-prompt'}
    store.update_job(jobid, payload=payload)
    class Client:
        def __init__(self, *args): pass
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'known-prompt'
            return SimpleNamespace(ok=True, output_files=['character.png'])
        def run_workflow(self, *args, **kwargs):
            raise AssertionError('Remote prompt must be resumed')
        def download_output(self, filename, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (128, 128), 'gray').save(path)
    monkeypatch.setattr('mangastudio.character_generation.ComfyClient', Client)
    generate_character_image(Worker(store), store.job(jobid))
    assert 'remote' not in store.job(jobid)['payload']
