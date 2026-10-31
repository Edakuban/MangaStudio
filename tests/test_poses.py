import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker, image_signature, pose_instructions, decode_plan, validate_chunk
from mangastudio.poses import generate_poses
from mangastudio.models import Settings


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data', start_worker=False)) as client:
        book = client.post('/api/demo').json()
        project = client.get('/api/projects/'+book['id']).json()
        chapter = client.get('/api/chapters/'+project['chapters'][0]['id']).json()
        yield client, project, chapter


def test_pose_roundtrip_and_image_signature(setup):
    client, project, chapter = setup
    p = chapter['scenes'][0]['panels'][0]
    char = project['characters'][0]
    p['characters'] = [char['id']]
    before = image_signature(project, p, project['characters'], Settings())
    p['character_poses'] = {char['id']: 'Kneeling, both hands holding a pendant.'}
    res = client.put('/api/chapters/'+chapter['id']+'/plan', json={'revision': chapter['revision'], 'scenes': chapter['scenes']})
    assert res.status_code == 200, res.text
    saved = res.json()['scenes'][0]['panels'][0]
    assert saved['character_poses'] == p['character_poses']
    assert image_signature(project, saved, project['characters'], Settings()) != before
    prompt = pose_instructions(saved, [char])
    assert char['name']+': Kneeling' in prompt and 'override any pose' in prompt
    saved['character_poses'][char['id']] = '  '
    assert image_signature(project, saved, project['characters'], Settings()) == before


def test_pose_job_preserves_manual_values_and_resumes_without_duplicate_ai(setup, monkeypatch):
    client, project, chapter = setup
    store = client.app.state.store
    ch = store.get('chapters', chapter['id'])
    p = ch['scenes'][0]['panels'][0]
    ids = [c['id'] for c in project['characters'][:2]]
    p['characters'] = ids
    p['character_poses'] = {ids[0]: 'My manual pose'}
    store.write('chapters', ch, project['id'], ch['position'])
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph)
            kwargs['progress']('pose-prompt')
            return SimpleNamespace(ok=True, text_outputs=[json.dumps({'character_poses': {'C1': 'Leaning forward, both hands raised.'}})])
    monkeypatch.setattr('mangastudio.poses.ComfyClient', Client)
    jobid = client.post('/api/chapters/'+chapter['id']+'/poses', json={'panel_id': p['id']}).json()['job_id']
    generate_poses(Worker(store), store.job(jobid))
    generate_poses(Worker(store), store.job(jobid))
    assert len(calls) == 1
    saved = store.get('chapters', ch['id'])['scenes'][0]['panels'][0]
    assert saved['character_poses'] == {ids[0]: 'My manual pose', ids[1]: 'Leaning forward, both hands raised.'}
    assert saved['image'] == p['image'] and saved['visual_prompt'] == p['visual_prompt']
    store.update_job(jobid, state='done')
    assert client.post('/api/chapters/'+chapter['id']+'/poses', json={'panel_id': 'missing'}).status_code == 404


def test_planner_maps_pose_names_and_rejects_unselected_characters(setup):
    client, project, chapter = setup
    scene = chapter['scenes'][0]
    p = scene['panels'][0]
    scene['panels'] = [p]
    p['characters'] = ['C1']
    p['character_poses'] = {'C1': 'Looking over the left shoulder.'}
    decoded = decode_plan(json.dumps({'summary': 'Test', 'scenes': [scene]}), project['characters'])
    panel = decoded.scenes[0].panels[0]
    assert panel.character_poses == {project['characters'][0]['id']: 'Looking over the left shoulder.'}
    panel.character_poses['unknown'] = 'Standing'
    with pytest.raises(ValueError, match='Körperhaltung'):
        validate_chunk(decoded, [(scene['source_start'], scene['source_excerpt'])], {project['characters'][0]['id']})


def test_image_worker_sends_pose_and_reference_together(setup, monkeypatch):
    from PIL import Image
    client, project, chapter = setup
    store = client.app.state.store
    char = project['characters'][0]
    char['image'] = 'pose-reference.png'
    Image.new('RGB', (64, 64), 'gray').save(store.asset(char['image']))
    store.write('characters', char, project['id'])
    ch = store.get('chapters', chapter['id'])
    p = ch['scenes'][0]['panels'][0]
    p['characters'] = [char['id']]
    p['character_poses'] = {char['id']: 'Kneeling, both hands holding the pendant.'}
    store.write('chapters', ch, project['id'], ch['position'])
    captured = []
    class Client:
        def __init__(self, *args): pass
        def upload_input(self, path, **kwargs):
            assert path == store.asset(char['image'])
            return 'reference.png'
        def run_workflow(self, graph, **kwargs):
            captured.append(graph)
            kwargs['progress']('image-prompt')
            return SimpleNamespace(ok=True, output_files=['out.png'])
        def download_output(self, name, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (64, 64), 'gray').save(target)
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    jobid = store.enqueue(project['id'], chapter['id'], 'images', {'panel_id': p['id'], 'missing_only': False})
    Worker(store).images(store.job(jobid))
    graph = captured[0]
    assert char['name']+': Kneeling' in graph['4']['inputs']['text']
    assert any(node['class_type'] == 'ReferenceLatent' for node in graph.values())


def test_failed_pose_response_does_not_change_panels_and_revision_conflicts_stop_retry(setup, monkeypatch):
    client, project, chapter = setup
    store = client.app.state.store
    p = chapter['scenes'][0]['panels'][0]
    ch = store.get('chapters', chapter['id'])
    ch['scenes'][0]['panels'][0]['characters'] = [project['characters'][0]['id']]
    store.write('chapters', ch, project['id'], ch['position'])
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            kwargs['progress']('bad-pose')
            return SimpleNamespace(ok=True, text_outputs=['{"character_poses":{"C99":"Unknown person"}}'])
    monkeypatch.setattr('mangastudio.poses.ComfyClient', Client)
    jobid = client.post('/api/chapters/'+chapter['id']+'/poses', json={'panel_id': p['id']}).json()['job_id']
    before = store.get('chapters', chapter['id'])
    with pytest.raises(ValueError, match='Ungültige'):
        generate_poses(Worker(store), store.job(jobid))
    assert store.get('chapters', chapter['id']) == before
    assert 'remote' not in store.job(jobid)['payload']
    before['revision'] += 1
    store.write('chapters', before, project['id'], before['position'])
    with pytest.raises(ValueError, match='Storyboard wurde geändert'):
        generate_poses(Worker(store), store.job(jobid))
