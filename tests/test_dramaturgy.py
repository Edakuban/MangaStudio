import copy
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker, image_signature
from mangastudio.dramaturgy import review_storyboard
from mangastudio.models import uid


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        book=client.post('/api/demo').json()
        project=client.get('/api/projects/'+book['id']).json()
        chapter=client.get('/api/chapters/'+project['chapters'][0]['id']).json()
        yield client,project,chapter


def proposal(action='replace',panel='P2',source=2):
    return {'action':action,'category':'missing_beat','panel':panel,'title':'Den Fund sichtbar machen',
        'reason':'Der entscheidende Fund soll als konkreter Handlungsschritt sichtbar werden.',
        'source_start':source,'source_end':source,
        'replacement':None if action=='remove' else {'description':'Mara öffnet ihr Notizbuch und betrachtet die Zeichnung.',
            'visual_prompt':'One adult archivist opening a notebook and looking down at the drawing.',
            'shot':'detail','beat':'detail','characters':['C1'],'character_poses':{'C1':'Both hands holding the open notebook.'},
            'bubbles':[],'caption':''}}


def stage(setup,monkeypatch,proposals=None):
    client,project,chapter=setup
    calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph)
            kwargs['progress']('review-'+str(len(calls)))
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'summary':'Fund und Reaktion deutlicher trennen.',
                'suggestions':proposals if proposals is not None else [proposal()]})])
    monkeypatch.setattr('mangastudio.dramaturgy.ComfyClient',Client)
    result=client.post('/api/chapters/'+chapter['id']+'/dramaturgy')
    assert result.status_code==200,result.text
    store=client.app.state.store
    jobid=result.json()['job_id']
    review_storyboard(Worker(store),store.job(jobid))
    store.update_job(jobid,state='done')
    current=client.get('/api/chapters/'+chapter['id']).json()
    return current,current['dramaturgy_review'],calls


def decision(client,chapter,review,finding,action='apply'):
    return client.post(f'/api/chapters/{chapter["id"]}/dramaturgy/{finding["id"]}',json={'review_id':review['id'],'action':action})


def test_review_is_staged_source_backed_and_resume_does_not_rescan(setup,monkeypatch):
    client,project,chapter=setup
    store=client.app.state.store
    before=store.get('chapters',chapter['id'])
    current,review,calls=stage(setup,monkeypatch)
    after=store.get('chapters',chapter['id'])
    assert after['scenes']==before['scenes'] and after['revision']==before['revision']
    finding=review['suggestions'][0]
    assert finding['status']=='pending' and not finding['stale']
    assert finding['source_excerpt'] in ' '.join(p['text'] for p in current['source_paragraphs'])
    assert finding['replacement']['characters']==[project['characters'][0]['id']]
    review_storyboard(Worker(store),store.job(review['id']))
    assert len(calls)==1


def test_apply_one_preserves_other_panels_assets_and_marks_old_image_stale(setup,monkeypatch):
    client,project,chapter=setup
    store=client.app.state.store
    ch=store.get('chapters',chapter['id']);target=ch['scenes'][1]['panels'][0]
    target['image']='existing.png';target['image_signature']=image_signature(project,target,project['characters'],store.settings())
    store.write('chapters',ch,project['id'],ch['position'])
    before=copy.deepcopy(ch)
    current,review,calls=stage(setup,monkeypatch,[proposal(),proposal('remove','P4')])
    res=decision(client,chapter,review,review['suggestions'][0])
    assert res.status_code==200,res.text
    saved=res.json();changed=saved['scenes'][1]['panels'][0]
    assert changed['image']=='existing.png' and changed['id']==target['id']
    assert changed['id'] in saved['stale_panels']
    assert changed['description'].startswith('Mara öffnet')
    old={p['id']:p for s in before['scenes'] for p in s['panels']}
    for scene in saved['scenes']:
        for p in scene['panels']:
            if p['id']!=changed['id']: assert p==old[p['id']]
    assert saved['dramaturgy_review']['suggestions'][1]['status']=='pending'
    assert decision(client,chapter,review,review['suggestions'][0]).status_code==409


def test_dismiss_changes_no_storyboard_or_revision(setup,monkeypatch):
    client,project,chapter=setup
    current,review,_=stage(setup,monkeypatch)
    result=decision(client,chapter,review,review['suggestions'][0],'dismiss')
    assert result.status_code==200
    assert result.json()['scenes']==current['scenes'] and result.json()['revision']==current['revision']
    assert result.json()['dramaturgy_review']['suggestions'][0]['status']=='dismissed'


def test_stale_target_rejected_but_unrelated_edit_allows_apply(setup,monkeypatch):
    client,project,chapter=setup
    current,review,_=stage(setup,monkeypatch)
    store=client.app.state.store
    ch=store.get('chapters',chapter['id'])
    ch['scenes'][0]['panels'][0]['caption']='Meine andere Änderung'
    ch['revision']+=1;store.write('chapters',ch,project['id'],ch['position'])
    assert decision(client,chapter,review,review['suggestions'][0]).status_code==200
    # A fresh review cannot overwrite manual work on its actual target.
    current,review,_=stage(setup,monkeypatch)
    ch=store.get('chapters',chapter['id']);ch['scenes'][1]['panels'][0]['caption']='Manuell verbessert'
    store.write('chapters',ch,project['id'],ch['position'])
    visible=client.get('/api/chapters/'+chapter['id']).json()['dramaturgy_review']
    assert visible['suggestions'][0]['stale']
    assert decision(client,chapter,review,review['suggestions'][0]).status_code==409
    assert store.get('chapters',chapter['id'])['scenes'][1]['panels'][0]['caption']=='Manuell verbessert'


@pytest.mark.parametrize('action',['insert_before','insert_after','insert_scene_before','insert_scene_after','remove'])
def test_insert_and_remove_actions_are_explicit_and_preserve_source(setup,monkeypatch,action):
    client,project,chapter=setup
    current,review,_=stage(setup,monkeypatch,[proposal(action,'P2')])
    before=sum(len(s['panels']) for s in current['scenes'])
    result=decision(client,chapter,review,review['suggestions'][0])
    assert result.status_code==200,result.text
    saved=result.json()
    assert sum(len(s['panels']) for s in saved['scenes'])==before+(-1 if action=='remove' else 1)
    assert saved['text']==chapter['text']
    assert saved['dramaturgy_review']['suggestions'][0]['status']=='applied'


@pytest.mark.parametrize('invalid',['source','character','panel'])
def test_invalid_source_or_character_never_changes_storyboard(setup,monkeypatch,invalid):
    client,project,chapter=setup
    store=client.app.state.store
    before=store.get('chapters',chapter['id'])
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            kwargs['progress']('invalid')
            bad=proposal()
            if invalid=='source':bad['source_end']=9999
            elif invalid=='character':bad['replacement']['characters']=['C999']
            else:bad['panel']='P999'
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[bad]})])
    monkeypatch.setattr('mangastudio.dramaturgy.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/dramaturgy').json()['job_id']
    with pytest.raises(ValueError,match='gültigen'):
        review_storyboard(Worker(store),store.job(jobid))
    assert store.get('chapters',chapter['id'])==before
    assert 'remote' not in store.job(jobid)['payload']


def test_scene_capacity_rejection_is_atomic(setup,monkeypatch):
    client,project,chapter=setup
    store=client.app.state.store
    ch=store.get('chapters',chapter['id']);scene=ch['scenes'][1]
    while len(scene['panels'])<6:
        p=copy.deepcopy(scene['panels'][-1]);p['id']=uid();scene['panels'].append(p)
    store.write('chapters',ch,project['id'],ch['position'])
    current,review,_=stage(setup,monkeypatch,[proposal('insert_after')])
    before=store.get('chapters',chapter['id'])
    result=decision(client,chapter,review,review['suggestions'][0])
    assert result.status_code==400 and 'sechs Panels' in result.text
    assert store.get('chapters',chapter['id'])==before


def test_mixed_review_keeps_only_valid_findings_and_reports_incomplete_review(setup,monkeypatch):
    client,project,chapter=setup;store=client.app.state.store;before=store.get('chapters',chapter['id'])
    bad=proposal();bad['source_end']=9999
    current,review,calls=stage(setup,monkeypatch,[bad,proposal()])
    assert len(calls)==3
    assert len(review['suggestions'])==1 and len(review['warnings'])==1
    assert 'Ungültige Fundstelle' in review['warnings'][0]
    assert current['scenes']==before['scenes'] and current['revision']==before['revision']
    assert review['suggestions'][0]['status']=='pending'


@pytest.mark.parametrize('accept_order',[(0,1),(1,0)])
def test_new_scenes_use_source_order_even_with_wrong_ai_side_and_reverse_acceptance(setup,monkeypatch,accept_order):
    client,project,chapter=setup;store=client.app.state.store
    ch=store.get('chapters',chapter['id'])
    ch['text']='\n\n'.join(f'Originalabsatz Nummer {n} mit belegter Handlung.' for n in range(1,21))
    ch['scenes']=ch['scenes'][:2]
    for s,first,last in zip(ch['scenes'],[1,13],[4,16]):
        s.update(source_start=first,source_end=last,source_excerpt=f'Originalabsatz Nummer {first} mit belegter Handlung.')
    store.write('chapters',ch,project['id'],ch['position'])
    original=copy.deepcopy(ch)
    later=proposal('insert_scene_before','P1',9)
    later['replacement'].update(description='Mara blickt erschrocken auf.',visual_prompt='Mara looking up in surprise.')
    current,review,calls=stage(setup,monkeypatch,[
        proposal('insert_scene_before','P1',5),later])
    assert len(calls)==1
    assert all(f['action']=='insert_scene_after' for f in review['suggestions'])
    assert all('Einfügeposition' in f['reason'] for f in review['suggestions'])
    for n in accept_order:
        res=decision(client,chapter,review,review['suggestions'][n])
        assert res.status_code==200,res.text
    saved=store.get('chapters',chapter['id'])
    assert [s['source_start'] for s in saved['scenes']]==[1,5,9,13]
    for scene in original['scenes']:
        assert next(s for s in saved['scenes'] if s['id']==scene['id'])==scene


@pytest.mark.parametrize('invalid',['source','scene','schema','timeout'])
def test_review_repairs_specific_error_before_publishing_and_resumes_correction(setup,monkeypatch,invalid):
    client,project,chapter=setup;store=client.app.state.store;before=store.get('chapters',chapter['id']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt)
            kwargs['progress']('review-repair-'+str(len(calls)))
            assert store.get('chapters',chapter['id'])==before
            assert not store.job(jobid)['payload'].get('completed_chunks',[])
            if len(calls)==1:
                bad=proposal()
                if invalid=='schema':bad['replacement']['shot']='invalid-private-value'
                elif invalid=='scene':bad['panel']='P1';bad['source_start']=bad['source_end']=2
                else:bad['source_end']=9999
                return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[bad]})])
            assert 'KONKRETER FEHLER:' in prompt
            if invalid=='schema':assert 'replacement.shot' in prompt and 'invalid-private-value' not in prompt
            elif invalid=='scene':assert 'außerhalb der Ankerszene' in prompt
            else:assert 'Ungültige Fundstelle' in prompt
            if invalid=='timeout':return SimpleNamespace(ok=False,error='COMFY_TIMEOUT: running')
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[proposal()]})])
        def wait_for_prompt(self,prompt_id,**kwargs):
            assert prompt_id=='review-repair-2'
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[proposal()]})])
    monkeypatch.setattr('mangastudio.dramaturgy.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/dramaturgy').json()['job_id']
    if invalid=='timeout':
        with pytest.raises(ValueError,match='COMFY_TIMEOUT'):review_storyboard(Worker(store),store.job(jobid))
        pending=store.job(jobid)
        assert pending['payload']['remote']['operation']=='dramaturgy:0:repair:1'
    review_storyboard(Worker(store),store.job(jobid))
    assert len(calls)==2
    after=store.get('chapters',chapter['id'])
    assert after['scenes']==before['scenes'] and after['revision']==before['revision']
    assert len(after['dramaturgy_review']['suggestions'])==1
    assert 'review_quality' not in store.job(jobid)['payload']


def test_timeout_retains_remote_review_prompt_and_resumes(setup,monkeypatch):
    client,project,chapter=setup;store=client.app.state.store
    calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('known-review')
            return SimpleNamespace(ok=False,error='COMFY_TIMEOUT: still running')
        def wait_for_prompt(self,prompt_id,**kwargs):
            assert prompt_id=='known-review'
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[proposal()]})])
    monkeypatch.setattr('mangastudio.dramaturgy.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/dramaturgy').json()['job_id']
    with pytest.raises(ValueError,match='COMFY_TIMEOUT'):
        review_storyboard(Worker(store),store.job(jobid))
    assert store.job(jobid)['payload']['remote']['prompt_id']=='known-review'
    # Profile writes can reorder SQLite rows; cached C1 must still mean the original person.
    original=project['characters'][0]
    store.write('characters',original,project['id'])
    review_storyboard(Worker(store),store.job(jobid))
    assert len(calls)==1
    assert store.get('chapters',chapter['id'])['dramaturgy_review']['suggestions']
    finding=store.get('chapters',chapter['id'])['dramaturgy_review']['suggestions'][0]
    assert finding['replacement']['characters']==[original['id']]


def test_wrong_chapter_review_and_busy_guard(setup,monkeypatch):
    client,project,chapter=setup
    current,review,_=stage(setup,monkeypatch)
    other=project['chapters'][1]
    assert decision(client,other,review,review['suggestions'][0]).status_code==409
    jobid=client.post('/api/chapters/'+chapter['id']+'/dramaturgy').json()['job_id']
    assert decision(client,chapter,review,review['suggestions'][0]).status_code==409
    client.app.state.store.update_job(jobid,state='failed')


def test_review_ignores_model_lettering_geometry_and_preserves_author_placement(setup,monkeypatch):
    from mangastudio.models import Bubble
    client,project,chapter=setup;store=client.app.state.store
    ch=store.get('chapters',chapter['id']);target=ch['scenes'][1]['panels'][0]
    target['bubbles']=[Bubble(speaker='Mara',text='Alt.',side='left',vertical='bottom',x=.123,y=.65,
        width=.45,height=.2,tail_x=.3,tail_y=.9,font_size=12,show_tail=False).model_dump()]
    store.write('chapters',ch,project['id'],ch['position'])
    before=copy.deepcopy(target['bubbles'][0]);suggestion=proposal()
    bad=Bubble(speaker='Mara',text='Was ist das?',shape='thought',side='right',vertical='top',x=.5,y=.1,
        width=.3,height=.3,tail_x=.8,tail_y=.6,font_size=8,show_tail=True).model_dump()
    suggestion['replacement']['bubbles']=[bad]
    current,review,calls=stage(setup,monkeypatch,[suggestion])
    assert len(calls)==1
    prompt=calls[0]['2']['inputs']['prompt']
    assert '"font_size"' not in prompt and '"tail_x"' not in prompt
    assert current['scenes'][1]['panels'][0]['bubbles'][0]==before
    finding=review['suggestions'][0]
    assert finding['replacement']['bubbles']==[{'speaker':'Mara','text':'Was ist das?','shape':'thought'}]
    result=decision(client,chapter,review,finding)
    assert result.status_code==200,result.text
    after=next(p for s in result.json()['scenes'] for p in s['panels'] if p['id']==target['id'])['bubbles'][0]
    assert after==before|{'text':'Was ist das?','shape':'thought'}


def test_unknown_bubble_fields_are_still_rejected(setup,monkeypatch):
    client,project,chapter=setup;store=client.app.state.store;before=store.get('chapters',chapter['id']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('unknown')
            p=proposal();p['replacement']['bubbles']=[{'text':'Hallo','unexpected':'private-value'}]
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'suggestions':[p]})])
    monkeypatch.setattr('mangastudio.dramaturgy.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/dramaturgy').json()['job_id']
    with pytest.raises(ValueError,match='unexpected') as exc:review_storyboard(Worker(store),store.job(jobid))
    assert len(calls)==3 and 'private-value' not in str(exc.value)
    assert store.get('chapters',chapter['id'])==before
