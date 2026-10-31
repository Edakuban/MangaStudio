from io import BytesIO
import json
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.models import CharacterDiscovery
from mangastudio.character_discovery import checked_candidates, match_existing, autoadd_characters
from mangastudio.engine import Worker


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data', start_worker=False)) as client:
        yield client


def demo(client):
    book = client.post('/api/demo').json()
    project = client.get('/api/projects/'+book['id']).json()
    chapter = client.get('/api/chapters/'+project['chapters'][0]['id']).json()
    return project, chapter


def test_delete_restore_preserves_images_and_panel_content(client):
    project, chapter = demo(client)
    char = project['characters'][0]
    affected = [p['id'] for s in chapter['scenes'] for p in s['panels'] if char['id'] in p['characters']]
    target = affected[0]
    image = BytesIO()
    Image.new('RGB', (2000, 3000), 'gray').save(image, 'PNG')
    uploaded = client.post(f'/api/chapters/{chapter["id"]}/panels/{target}/image', files={'file': ('p.png', image.getvalue())}).json()
    old_panels = {p['id']: p for s in uploaded['scenes'] for p in s['panels']}
    res = client.delete(f'/api/projects/{project["id"]}/characters/{char["id"]}')
    assert res.status_code == 200, res.text
    assert res.json()['recoverable']
    current = client.get('/api/chapters/'+chapter['id']).json()
    assert current['revision'] > uploaded['revision']
    assert target in current['stale_panels']
    for scene in current['scenes']:
        for panel in scene['panels']:
            assert char['id'] not in panel['characters']
            assert panel['description'] == old_panels[panel['id']]['description']
            assert panel['image'] == old_panels[panel['id']]['image']
    listed = client.get('/api/projects/'+project['id']).json()
    assert char['id'] not in {c['id'] for c in listed['characters']}
    assert char['id'] in {c['id'] for c in listed['deleted_characters']}
    restored = client.post(f'/api/projects/{project["id"]}/characters/{char["id"]}/restore')
    assert restored.status_code == 200
    current = client.get('/api/chapters/'+chapter['id']).json()
    assert target not in current['stale_panels']
    assert [p['id'] for s in current['scenes'] for p in s['panels'] if char['id'] in p['characters']] == affected


def test_delete_ownership_busy_and_repeat(client):
    project, chapter = demo(client)
    char = project['characters'][0]
    other = client.post('/api/import', files={'file': ('second.txt', b'A second book.')}).json()
    assert client.delete(f'/api/projects/{other["id"]}/characters/{char["id"]}').status_code == 404
    job = client.post(f'/api/chapters/{chapter["id"]}/characters/autoadd', json={}).json()['job_id']
    assert client.delete(f'/api/projects/{project["id"]}/characters/{char["id"]}').status_code == 409
    client.app.state.store.update_job(job, state='done')
    assert client.delete(f'/api/projects/{project["id"]}/characters/{char["id"]}').status_code == 200
    assert client.delete(f'/api/projects/{project["id"]}/characters/{char["id"]}').status_code == 404
    assert client.post(f'/api/projects/{other["id"]}/characters/{char["id"]}/restore').status_code == 404


def test_autoadd_full_chapter_duplicate_alias_and_idempotence(client, monkeypatch):
    project, chapter = demo(client)
    store = client.app.state.store
    original = json.loads(json.dumps(project['characters']))
    # Source has the same named person at the beginning and after a chunk boundary.
    text = 'Mara steht am Bahnhof. Juna trägt einen roten Mantel. '+' '.join(['Regen']*900)+'\n\nJuna spricht mit Ivo. '+' '.join(['Regen']*900)
    saved = store.get('chapters', chapter['id'])
    saved['text'] = text
    store.write('chapters', saved, project['id'], saved['position'])
    calls = []
    class Client:
        def __init__(self, *args):
            pass
        def run_workflow(self, graph, **kwargs):
            prompt = graph['2']['inputs']['prompt']
            source = prompt.split('QUELLE:\n')[1].split('\nSCHEMA:')[0]
            import re
            rows = [(int(n), content) for n, content in re.findall(r'\[(\d+)\] ([\s\S]*?)(?=\n\n\[\d+\]|$)', source)]
            number = next(n for n, content in rows if 'Juna' in content)
            calls.append(prompt)
            kwargs['progress']('scan-'+str(len(calls)))
            result = {'characters': [
                {'name': 'Juna', 'aliases': [], 'description': 'Trägt einen roten Mantel.', 'kind': 'named', 'source_start': number, 'source_end': number, 'mention': 'Juna'}]}
            if len(calls) == 1:
                result['characters'].append({'name': 'Mara', 'aliases': [], 'description': 'Steht am Bahnhof.', 'kind': 'named', 'source_start': number, 'source_end': number, 'mention': 'Mara'})
            return SimpleNamespace(ok=True, text_outputs=[json.dumps(result if len(calls) == 1 else result['characters'])])
    monkeypatch.setattr('mangastudio.character_discovery.ComfyClient', Client)
    ident = client.post(f'/api/chapters/{chapter["id"]}/characters/autoadd', json={}).json()['job_id']
    autoadd_characters(Worker(store), store.job(ident))
    assert len(calls) == 2
    assert all('BISHER' not in call and 'Kapitel 2' not in call for call in calls)
    cast = store.list('characters', project['id'])
    assert len([c for c in cast if c['name'] == 'Juna']) == 1
    assert [c for c in cast if c['id'] in {x['id'] for x in original}] == original
    result = store.job(ident)['payload']['result']
    assert len(result['added']) == 1 and result['existing'] == 2
    assert next(c for c in cast if c['name'] == 'Juna')['image'] == ''
    # A resumed completed job is a no-op, not another scan or duplicate insert.
    autoadd_characters(Worker(store), store.job(ident))
    assert len(calls) == 2


def test_autoadd_skips_deleted_names_and_validates_mentions(client, monkeypatch):
    project, chapter = demo(client)
    char = project['characters'][0]
    client.delete(f'/api/projects/{project["id"]}/characters/{char["id"]}')
    store = client.app.state.store
    class Client:
        def __init__(self, *args):
            pass
        def run_workflow(self, graph, **kwargs):
            kwargs['progress']('scan')
            return SimpleNamespace(ok=True, text_outputs=[json.dumps({'characters': [
                {'name': 'Mara', 'description': 'Sie betritt die Station.', 'source_start': 1, 'source_end': 1, 'mention': 'Mara'},
                {'name': 'Erfundene Person', 'description': 'Steht nicht im Kapitel.', 'source_start': 1, 'source_end': 1, 'mention': 'Mara'}]})])
    monkeypatch.setattr('mangastudio.character_discovery.ComfyClient', Client)
    ident = client.post(f'/api/chapters/{chapter["id"]}/characters/autoadd', json={}).json()['job_id']
    autoadd_characters(Worker(store), store.job(ident))
    result = store.job(ident)['payload']['result']
    assert result['deleted'] == 1 and result['unverified'] == 1 and result['added'] == []


def test_alias_matching_avoids_similar_names_and_ambiguous_short_names():
    assert match_existing({'name': 'AMARA', 'aliases': []}, [{'name': 'Lady Amara', 'aliases': 'Amara'}]) == 'existing'
    assert match_existing({'name': 'Anna Schmidt', 'aliases': ['Anna']}, [{'name': 'Anna Müller', 'aliases': 'Anna'}]) == 'new'
    assert match_existing({'name': 'Anna', 'aliases': []}, [{'name': 'Anna Müller', 'aliases': 'Anna'}, {'name': 'Anna Schmidt', 'aliases': 'Anna'}]) == 'ambiguous'
    result = CharacterDiscovery.model_validate({'characters': [{'name': 'Anna', 'description': 'Kurzes Haar.', 'source_start': 1, 'source_end': 1, 'mention': 'Anna'}]})
    assert checked_candidates(result, [(1, 'Annabelle kommt an.')]) == ([], 1)
