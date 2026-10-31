import copy
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker
from mangastudio.book_style import analyze_book_style


STYLE='Expressive manga illustration, precise ink contours, warm amber lamplight and cool blue fog, weathered industrial architecture, consistent restrained colors and readable cinematic compositions.'


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        p=client.post('/api/import',files={'file':('novel.txt',b'Chapter 1\n\nAn archivist crosses a foggy industrial harbor.\n\nChapter 2\n\nAt dawn amber lamps illuminate copper pipes and stone walls.')}).json()
        yield client,client.app.state.store,p


def start(setup):
    client,store,p=setup
    result=client.post('/api/projects/'+p['id']+'/style-analysis')
    assert result.status_code==200,result.text
    return store.job(result.json()['job_id'])


def response(op):
    data={'style':STYLE,'rationale':'Nebel, Kupfer und warmes Licht prägen die Schauplätze; die Palette ist ein gestalterischer Vorschlag.'} if 'compose' in op else {
        'notes':'Industrial harbor, copper pipes, fog and amber lamps recur; maintain prior observations across chapters.',
        'uncertainty':'Die genaue Epoche ist nicht ausdrücklich benannt.'}
    return SimpleNamespace(ok=True,text_outputs=[json.dumps(data)])


def test_reads_all_chapters_and_stages_without_changing_style_or_story(setup,monkeypatch):
    client,store,p=setup;before=store.get('projects',p['id']);chapters=copy.deepcopy(store.list('chapters',p['id']));calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt);kwargs['progress']('style-'+str(len(calls)))
            if len(calls)==2:assert 'Industrial harbor' in prompt
            return response('compose' if len(calls)==3 else 'notes')
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    job=start(setup);assert client.post('/api/projects/'+p['id']+'/style-analysis').status_code==409
    analyze_book_style(Worker(store),job)
    after=store.get('projects',p['id'])
    assert after['style']==before['style'] and after['direction']==before['direction'] and after['monochrome']==before['monochrome']
    assert store.list('chapters',p['id'])==chapters
    assert after['style_draft']['style']==STYLE and after['style_draft']['sections']==2
    assert 'foggy industrial harbor' in calls[0] and 'copper pipes and stone walls' in calls[1]
    assert not client.get('/api/projects/'+p['id']).json()['style_draft_stale']
    analyze_book_style(Worker(store),store.job(job['id']));assert len(calls)==3
    store.update_job(job['id'],state='done')
    result=client.put('/api/projects/'+p['id'],json={k:after[k] for k in ('title','direction','monochrome')}|{'style':STYLE})
    assert result.status_code==200 and result.json()['style']==STYLE


@pytest.mark.parametrize('phase',['notes','compose'])
def test_timeout_resumes_known_style_prompt_without_reanalyzing_finished_sections(setup,monkeypatch,phase):
    client,store,p=setup;calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            op='compose' if 'Formuliere aus' in graph['2']['inputs']['prompt'] else 'notes'
            calls.append(op);kwargs['progress']('known-'+op)
            if op==phase:return SimpleNamespace(ok=False,error='COMFY_TIMEOUT: running')
            return response(op)
        def wait_for_prompt(self,prompt_id,**kwargs):
            assert prompt_id=='known-'+phase
            return response(phase)
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    job=start(setup)
    with pytest.raises(ValueError,match='COMFY_TIMEOUT'):analyze_book_style(Worker(store),job)
    pending=store.job(job['id']);assert pending['payload']['remote']['prompt_id']=='known-'+phase
    if phase=='compose':assert len(pending['payload']['completed_notes'])==2
    # For notes, avoid a second timeout after the resumed first section.
    if phase=='notes':
        def success(self,graph,**kwargs):
            op='compose' if 'Formuliere aus' in graph['2']['inputs']['prompt'] else 'notes'
            calls.append(op);kwargs['progress']('next');return response(op)
        monkeypatch.setattr(Client,'run_workflow',success)
    analyze_book_style(Worker(store),pending)
    assert calls==['notes','notes','compose']
    assert store.get('projects',p['id'])['style_draft']['style']==STYLE


def test_schema_failure_is_bounded_keeps_settings_and_resumes_from_notes(setup,monkeypatch):
    client,store,p=setup;before=store.get('projects',p['id']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt);kwargs['progress']('p-'+str(len(calls)))
            if 'Formuliere aus' not in prompt:return response('notes')
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'style':'private-invalid','rationale':'short'})])
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    job=start(setup)
    with pytest.raises(ValueError,match='zwei Korrekturen') as exc:analyze_book_style(Worker(store),job)
    assert len(calls)==5 and 'private-invalid' not in str(exc.value) and 'private-invalid' not in calls[-1]
    assert store.get('projects',p['id'])==before
    assert len(store.job(job['id'])['payload']['completed_notes'])==2


def test_source_change_rejects_resume_and_marks_existing_draft_stale(setup,monkeypatch):
    client,store,p=setup;job=start(setup)
    chapter=store.list('chapters',p['id'])[0];chapter['text']+=' New paragraph.';store.write('chapters',chapter,p['id'],chapter['position'])
    with pytest.raises(ValueError,match='Buchtext oder Kapitel'):analyze_book_style(Worker(store),job)
    book=store.get('projects',p['id']);book['style_draft']={'source_signature':job['payload']['source_signature']};store.write('projects',book)
    assert client.get('/api/projects/'+p['id']).json()['style_draft_stale']


def test_source_change_during_generation_does_not_publish_draft(setup,monkeypatch):
    client,store,p=setup
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            kwargs['progress']('p');op='compose' if 'Formuliere aus' in graph['2']['inputs']['prompt'] else 'notes'
            if op=='compose':
                chapter=store.list('chapters',p['id'])[0];chapter['text']+=' Changed source.';store.write('chapters',chapter,p['id'],chapter['position'])
            return response(op)
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    with pytest.raises(ValueError,match='Buchtext wurde geändert'):analyze_book_style(Worker(store),start(setup))
    assert not store.get('projects',p['id']).get('style_draft')


def test_empty_book_and_unknown_project_do_not_enqueue(setup):
    client,store,p=setup
    for c in store.list('chapters',p['id']):
        c['text']='';store.write('chapters',c,p['id'],c['position'])
    assert client.post('/api/projects/'+p['id']+'/style-analysis').status_code==400
    assert client.post('/api/projects/'+'f'*32+'/style-analysis').status_code==404
    assert not store.jobs(p['id'])


def test_long_internal_notes_are_preserved_and_context_stays_bounded(setup,monkeypatch):
    client,store,p=setup;calls=[]
    long_uncertainty='Unklare Epoche und wechselnde Lichtquellen. '*25
    long_notes='Belegte Materialien und gegensätzliche Schauplätze bleiben wichtig. '*45
    assert len(long_uncertainty)>500 and len(long_notes)>2200
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt);kwargs['progress']('long-notes-'+str(len(calls)))
            if len(calls)>1:
                assert long_uncertainty not in prompt and long_notes not in prompt
                assert 'gekürzte Kontextansicht' in prompt
            if len(calls)==3:return response('compose')
            assert '"maxLength": 500' in prompt
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'notes':long_notes,'uncertainty':long_uncertainty})])
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    job=start(setup);before=store.get('projects',p['id'])['style']
    analyze_book_style(Worker(store),job)
    assert len(calls)==3
    for note in store.job(job['id'])['payload']['completed_notes']:
        assert note['uncertainty']==long_uncertainty and note['notes']==long_notes
    saved=store.get('projects',p['id']);assert saved['style']==before and saved['style_draft']['style']==STYLE


def test_context_removes_runaway_word_repetitions_without_mutating_notes():
    from mangastudio.book_style import notes_context
    raw={'notes':'Dunkles Tuschebild. '+('Asche, '*1000)+'Warm light returns.', 'uncertainty':'Epoche unklar. '*100}
    before=copy.deepcopy(raw);context=notes_context(raw)
    assert raw==before
    assert len(context['notes'])<=2200 and len(context['uncertainty'])<=500
    assert 'Asche, Asche' not in context['notes'] and 'Warm light returns.' in context['notes']


def test_truncated_json_is_retried_without_saving_partial_notes(setup,monkeypatch):
    client,store,p=setup;calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt);kwargs['progress']('json-'+str(len(calls)))
            assert graph['2']['inputs']['max_length']==3000
            if len(calls)==1:return SimpleNamespace(ok=True,text_outputs=['{"notes":"Asche, Asche,'])
            if len(calls)==2:
                assert 'abgeschnitten' in prompt
                assert not store.job(job['id'])['payload'].get('completed_notes',[])
            return response('compose' if 'Formuliere aus' in prompt else 'notes')
    monkeypatch.setattr('mangastudio.book_style.ComfyClient',Client)
    job=start(setup);analyze_book_style(Worker(store),job)
    assert len(calls)==4 and len(store.job(job['id'])['payload']['completed_notes'])==2
    assert store.get('projects',p['id'])['style_draft']['style']==STYLE
