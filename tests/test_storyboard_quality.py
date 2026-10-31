import copy
import json
from types import SimpleNamespace
import pytest
from mangastudio.storyboard_quality import repeated_panels, plan_distinct_chunk
from mangastudio.engine import Worker
from mangastudio.store import Store
from mangastudio.importer import import_book
from mangastudio.models import Settings


def panel(text='Samuel standing in a children room looking sadly out the window wearing a simple shirt and pants'):
    return {'description': text, 'visual_prompt': text, 'shot': 'medium', 'bubbles': [], 'caption': ''}


def scenes(*panels):
    return [{'title': 'Scene', 'source_start': 1, 'source_end': 1, 'panels': list(panels)}]


def test_duplicate_detection_spans_scenes_and_previous_chunks():
    base = panel()
    similar = panel('A young boy named Samuel standing in a children room looking sadly out the window wearing a simple shirt and pants')
    assert repeated_panels(scenes(base, copy.deepcopy(base)))
    assert repeated_panels(scenes(similar), scenes(base))
    assert repeated_panels(scenes(base)+scenes(copy.deepcopy(base)))
    assert not repeated_panels(scenes(base, panel('A child kneeling on the floor examining a small metal pendant in both hands.')))


def test_intentional_dialogue_or_shot_changes_are_allowed():
    one, two = panel(), panel()
    two['bubbles'] = [{'speaker': 'Samuel', 'text': 'Warum?'}]
    assert not repeated_panels(scenes(one, two))

    two = panel()
    two['shot'] = 'detail'
    assert not repeated_panels(scenes(one, two))
    two = panel()
    two['caption'] = 'Drei Jahre später.'
    assert not repeated_panels(scenes(one, two))


def test_profile_copy_detection_ignores_short_features_and_scene_actions():
    from mangastudio.storyboard_quality import copied_character_profiles
    profile='Adult hunter with dark tousled hair, a long black leather coat, tall boots, a silver belt buckle, a shoulder holster and a confident relaxed expression.'
    assert copied_character_profiles(scenes(panel(profile)),[{'description':profile}])
    assert not copied_character_profiles(scenes(panel('The hunter kneels beside the ashes and lifts a pendant with both hands.')),[{'description':profile}])
    assert not copied_character_profiles(scenes(panel('Dark hair')),[{'description':'Dark hair'}])


def test_profile_copy_is_repaired_without_echoing_profile_or_replacing_finished_chunks(tmp_path,monkeypatch):
    from mangastudio.engine import decode_plan
    from mangastudio.models import uid
    store,job=setup(tmp_path)
    profile='Adult hunter with dark tousled hair, a long black leather coat, tall boots, a silver belt buckle, a shoulder holster and a confident relaxed expression.'
    char={'id':uid(),'name':'Samuel','aliases':'Sam','description':profile,'image':''}
    store.write('characters',char,job['project_id'])
    source=[[(1,'Samuel enters a room.')],[(2,'Samuel opens a notebook.')]]
    monkeypatch.setattr('mangastudio.engine.chunks',lambda text:source)
    finished=decode_plan(answer(panel('Samuel enters a room.')).text_outputs[0],[char],source[0]).model_dump()
    job['payload']['completed_chunks']=[copy.deepcopy(finished)];store.update_job(job['id'],payload=job['payload'])
    calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt)
            assert profile not in prompt
            assert store.job(job['id'])['payload']['completed_chunks']==[finished]
            kwargs['progress']('profile-'+str(len(calls)))
            p=panel('Samuel opens a notebook.');p['characters']=['C1']
            if len(calls)==1:p['visual_prompt']=profile
            else:assert 'Bildprompt kopiert ein Charakterprofil' in prompt
            s=scenes(p);s[0]['source_start']=s[0]['source_end']=2
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'summary':'Der Fund','scenes':s})])
    monkeypatch.setattr('mangastudio.engine.ComfyClient',Client)
    Worker(store).plan(job)
    assert len(calls)==2
    assert store.job(job['id'])['payload']['completed_chunks'][0]==finished
    saved=store.get('chapters',job['chapter_id'])
    assert saved['scenes'][0]==finished['scenes'][0]
    assert saved['scenes'][1]['panels'][0]['visual_prompt']=='Samuel opens a notebook.'


def setup(tmp_path):
    store = Store(tmp_path/'data')
    book = import_book(store, 'test.txt', b'Kapitel 1\n\nSamuel enters the room and opens a notebook. Then he raises his head.')
    chapter = store.list('chapters', book['id'])[0]
    jobid = store.enqueue(book['id'], chapter['id'], 'plan', {})
    return store, store.job(jobid)


def answer(*panels):
    return SimpleNamespace(ok=True, text_outputs=[json.dumps({'summary': 'Ankunft und Entdeckung', 'scenes': scenes(*panels)})])


def test_duplicate_response_is_repaired_before_worker_checkpoints(tmp_path, monkeypatch):
    store, job = setup(tmp_path)
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph['2']['inputs']['prompt'])
            kwargs['progress']('prompt-'+str(len(calls)))
            if len(calls) == 1:
                return answer(panel(), panel())
            assert not store.job(job['id'])['payload'].get('completed_chunks', [])
            return answer(panel('Samuel enters the room.'), panel('Samuel opens the notebook.'))
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    Worker(store).plan(job)
    assert len(calls) == 2 and 'ÜBERARBEITUNG ERFORDERLICH' in calls[1]
    saved = store.get('chapters', job['chapter_id'])
    assert len(saved['scenes'][0]['panels']) == 2
    assert not repeated_panels(saved['scenes'])
    assert len(store.job(job['id'])['payload']['completed_chunks']) == 1


@pytest.mark.parametrize('mode', ['repair', 'exhausted', 'timeout'])
@pytest.mark.parametrize('field', ['shot', 'beat'])
def test_schema_repair_keeps_validation_and_checkpoint_guards(tmp_path, monkeypatch, mode, field):
    store, job = setup(tmp_path)
    before = store.get('chapters', job['chapter_id'])
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph['2']['inputs']['prompt'])
            assert store.get('chapters', job['chapter_id']) == before
            assert not store.job(job['id'])['payload'].get('completed_chunks', [])
            kwargs['progress']('schema-'+str(len(calls)))
            if len(calls) == 1 or mode == 'exhausted':
                bad = panel('Samuel enters the room.')
                bad[field] = 'invalid-private-value'
                return answer(bad)
            assert 'scenes.0.panels.0.'+field in calls[-1]
            assert 'invalid-private-value' not in calls[-1]
            if mode == 'timeout':
                return SimpleNamespace(ok=False, error='COMFY_TIMEOUT: running')
            return answer(panel('Samuel enters the room.'))
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'schema-2'
            return answer(panel('Samuel enters the room.'))
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    if mode == 'exhausted':
        with pytest.raises(ValueError, match='zwei Überarbeitungen.*Schemafehler') as error:
            Worker(store).plan(job)
        assert 'invalid-private-value' not in str(error.value)
        assert len(calls) == 3
        assert store.get('chapters', job['chapter_id']) == before
        assert not store.job(job['id'])['payload'].get('completed_chunks', [])
        return
    if mode == 'timeout':
        with pytest.raises(ValueError, match='COMFY_TIMEOUT'):
            Worker(store).plan(job)
        pending = store.job(job['id'])
        assert pending['payload']['remote']['operation'] == 'plan:0:repair:1'
        Worker(store).plan(pending)
    else:
        Worker(store).plan(job)
    assert len(calls) == 2
    assert len(store.job(job['id'])['payload']['completed_chunks']) == 1
    assert store.get('chapters', job['chapter_id'])['scenes'][0]['panels'][0]['shot'] == 'medium'


def test_repeated_failures_are_bounded_and_do_not_replace_chapter(tmp_path, monkeypatch):
    store, job = setup(tmp_path)
    before = store.get('chapters', job['chapter_id'])
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph)
            kwargs['progress']('same-'+str(len(calls)))
            return answer(panel(), panel())
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    with pytest.raises(ValueError, match='zwei Überarbeitungen'):
        Worker(store).plan(job)
    assert len(calls) == 3
    assert store.get('chapters', job['chapter_id']) == before
    assert not store.job(job['id'])['payload'].get('completed_chunks', [])


def test_repair_timeout_keeps_remote_operation_and_resumes(tmp_path, monkeypatch):
    store, job = setup(tmp_path)
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph)
            kwargs['progress']('repair-prompt' if len(calls) == 2 else 'first-prompt')
            if len(calls) == 1:
                return answer(panel(), panel())
            return SimpleNamespace(ok=False, error='COMFY_TIMEOUT: still running')
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'repair-prompt'
            return answer(panel('Samuel enters.'), panel('Samuel opens his notebook.'))
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    with pytest.raises(ValueError, match='COMFY_TIMEOUT'):
        Worker(store).plan(job)
    pending = store.job(job['id'])
    assert pending['payload']['remote']['operation'] == 'plan:0:repair:1'
    Worker(store).plan(pending)
    assert len(calls) == 2
    assert not repeated_panels(store.get('chapters', job['chapter_id'])['scenes'])


def ordered_answer(reverse=False):
    items = [
        {'title': 'Ankunft', 'source_start': 1, 'source_end': 1,
         'panels': [panel('Samuel enters the room.')]},
        {'title': 'Fund', 'source_start': 2, 'source_end': 2,
         'panels': [panel('Samuel opens the notebook.')]},
    ]
    return SimpleNamespace(ok=True, text_outputs=[json.dumps({
        'summary': 'Ankunft und Fund', 'scenes': items[::-1] if reverse else items})])


@pytest.mark.parametrize('mode', ['repair', 'exhausted', 'timeout'])
def test_source_order_repair_is_bounded_durable_and_never_checkpoints_invalid_scenes(tmp_path, monkeypatch, mode):
    store, job = setup(tmp_path)
    before = store.get('chapters', job['chapter_id'])
    monkeypatch.setattr('mangastudio.engine.chunks', lambda text: [[
        (1, 'Samuel enters the room.'), (2, 'Samuel opens the notebook.')]])
    calls = []
    class Client:
        def __init__(self, *args): pass
        def run_workflow(self, graph, **kwargs):
            calls.append(graph['2']['inputs']['prompt'])
            assert not store.job(job['id'])['payload'].get('completed_chunks', [])
            assert store.get('chapters', job['chapter_id']) == before
            kwargs['progress']('order-'+str(len(calls)))
            if len(calls) == 1 or mode == 'exhausted':
                return ordered_answer(reverse=True)
            assert 'aufsteigender source_start-Reihenfolge' in calls[-1]
            if mode == 'timeout':
                return SimpleNamespace(ok=False, error='COMFY_TIMEOUT: running')
            return ordered_answer()
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'order-2'
            return ordered_answer()
    monkeypatch.setattr('mangastudio.engine.ComfyClient', Client)
    if mode == 'exhausted':
        with pytest.raises(ValueError, match='zwei Überarbeitungen.*Buchreihenfolge'):
            Worker(store).plan(job)
        assert len(calls) == 3
        assert store.get('chapters', job['chapter_id']) == before
        assert not store.job(job['id'])['payload'].get('completed_chunks', [])
        return
    if mode == 'timeout':
        with pytest.raises(ValueError, match='COMFY_TIMEOUT'):
            Worker(store).plan(job)
        pending = store.job(job['id'])
        assert pending['payload']['remote']['operation'] == 'plan:0:repair:1'
        Worker(store).plan(pending)
    else:
        Worker(store).plan(job)
    assert len(calls) == 2
    saved = store.get('chapters', job['chapter_id'])
    assert [s['source_start'] for s in saved['scenes']] == [1, 2]
    assert [s['source_excerpt'] for s in saved['scenes']] == [
        'Samuel enters the room.', 'Samuel opens the notebook.']
    assert len(store.job(job['id'])['payload']['completed_chunks']) == 1

