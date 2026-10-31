import copy
import json
from types import SimpleNamespace
import pytest
from mangastudio.models import uid
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker
from mangastudio.page_flow import flow_errors,spreads,structure_signature,plan_page_flow,render_flow
from mangastudio.layout import pages_for_chapter,book_pages


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        project=client.post('/api/demo').json()
        book=client.get('/api/projects/'+project['id']).json()
        chapter=client.get('/api/chapters/'+book['chapters'][0]['id']).json()
        yield client,book,chapter


def page(ids,turn='none',layout='balanced',composition='balanced'):
    return {'panels':ids,'turn':turn,'layout':layout,'composition':composition,'rhythm':'calm','reason':'Ein lesbarer Seitenrhythmus.'}


def test_spread_pairing_and_page_turn_validation():
    ids=['a','b','c']
    plan={'pages':[page(['a'],'setup'),page(['b'],'reveal'),page(['c'])]}
    assert not flow_errors(plan,ids,1)
    assert any('derselben Doppelseite' in e for e in flow_errors(plan,ids,2))
    for direction,side in [('rtl','left'),('ltr','right')]:
        groups=spreads([{'number':i} for i in [1,2,3]],direction)
        assert len(groups)==2 and groups[0][side]['number']==1
        assert {p['number'] for p in groups[1].values()}=={2,3}


@pytest.mark.parametrize('pages',[
    [page(['a','a'])], [page(['b','a'])], [page(['a'])],
    [page(['a','b'],layout='full_bleed')],
    [page(['a','b'],layout='dynamic',composition='wide_finish')],
    [page(['a'],'setup'),page(['b'])],
    [page(['a'],'reveal'),page(['b'])],
])
def test_invalid_plans_rejected(pages):
    assert flow_errors({'pages':pages},['a','b'])


def stage(setup,monkeypatch):
    client,book,chapter=setup;calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('flow-prompt')
            # Exactly eight source panels, grouped across the original scene boundary.
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'summary':'Aufbau und Enthüllung getrennt.',
                'pages':[page(['P1','P2','P3'],'setup'),page(['P4'],'reveal','full_bleed'),page(['P5','P6','P7','P8'],composition='wide_finish')]})])
    monkeypatch.setattr('mangastudio.page_flow.ComfyClient',Client)
    result=client.post('/api/chapters/'+chapter['id']+'/page-flow');assert result.status_code==200,result.text
    store=client.app.state.store;jobid=result.json()['job_id']
    plan_page_flow(Worker(store),store.job(jobid));store.update_job(jobid,state='done')
    return client.get('/api/chapters/'+chapter['id']+'/page-flow').json(),calls


def test_proposal_preview_and_apply_do_not_rewrite_story_or_images(setup,monkeypatch):
    client,book,chapter=setup;store=client.app.state.store
    before=store.get('chapters',chapter['id']);before_pages=pages_for_chapter(before,book['direction'])
    view,calls=stage(setup,monkeypatch)
    unchanged=store.get('chapters',chapter['id'])
    assert unchanged['scenes']==before['scenes'] and unchanged['revision']==before['revision']
    assert pages_for_chapter(unchanged,book['direction'])==before_pages
    assert not view['errors'] and [len(p['panels']) for p in view['proposed_pages']]==[3,1,4]
    body={'action':'apply','proposal_id':view['proposal']['id'],'plan':view['proposal']['plan']}
    result=client.post('/api/chapters/'+chapter['id']+'/page-flow/decide',json=body)
    assert result.status_code==200,result.text
    saved=store.get('chapters',chapter['id'])
    assert saved['scenes']==before['scenes']
    assert [len(p['panels']) for p in result.json()['pages']]==[3,1,4]
    assert result.json()['pages'][1]['layout']=='full_bleed'
    plan_page_flow(Worker(store),store.job(view['proposal']['id']));assert len(calls)==1


def test_manual_preview_is_read_only_and_rejects_skipped_panels(setup,monkeypatch):
    client,book,chapter=setup;view,_=stage(setup,monkeypatch)
    store=client.app.state.store;before=store.get('chapters',chapter['id'])
    plan=copy.deepcopy(view['proposal']['plan']);plan['pages'][0]['panels'].pop()
    preview=client.post('/api/chapters/'+chapter['id']+'/page-flow/preview',json=plan)
    assert preview.status_code==200 and preview.json()['errors']
    assert store.get('chapters',chapter['id'])==before
    result=client.post('/api/chapters/'+chapter['id']+'/page-flow/decide',json={'action':'apply','proposal_id':view['proposal']['id'],'plan':plan})
    assert result.status_code==409 and store.get('chapters',chapter['id'])==before


@pytest.mark.parametrize('change',['story','offset'])
def test_stale_story_and_global_page_offset_block_adoption(setup,monkeypatch,change):
    client,book,chapter=setup;view,_=stage(setup,monkeypatch)
    store=client.app.state.store;ch=store.get('chapters',chapter['id'])
    if change=='story':
        ch['scenes'][0]['panels'][0]['description']='Meine neue Fassung'
        store.write('chapters',ch,book['id'],ch['position'])
    else:
        prior=copy.deepcopy(ch);prior['id']=uid();prior['position']=0;prior['scenes']=prior['scenes'][:1]
        store.write('chapters',prior,book['id'],0)
    result=client.post('/api/chapters/'+chapter['id']+'/page-flow/decide',json={'action':'apply','proposal_id':view['proposal']['id']})
    assert result.status_code==409
    assert client.get('/api/chapters/'+chapter['id']+'/page-flow').json()['proposal']['stale']


def test_reset_restore_and_global_numbering(setup,monkeypatch):
    client,book,chapter=setup;view,_=stage(setup,monkeypatch)
    endpoint='/api/chapters/'+chapter['id']+'/page-flow/decide'
    assert client.post(endpoint,json={'action':'apply','proposal_id':view['proposal']['id']}).status_code==200
    assert client.post(endpoint,json={'action':'reset'}).json()['page_flow']['active']['enabled'] is False
    restored=client.post(endpoint,json={'action':'restore'})
    assert restored.status_code==200 and restored.json()['page_flow']['active']['enabled'] is True
    second=client.get('/api/chapters/'+book['chapters'][1]['id']).json()
    assert second['pages'][0]['number']==4
    assert second['page_flow']['start_page']==4
    store=client.app.state.store
    pdf_pages=book_pages(store.list('chapters',book['id']),book['direction'])
    assert [p['number'] for p in pdf_pages]==list(range(1,len(pdf_pages)+1))


def test_composition_gives_last_panel_a_large_full_width_area(setup):
    client,book,chapter=setup
    ids=[p['id'] for s in chapter['scenes'] for p in s['panels']][:4]
    result=render_flow(chapter,{'pages':[page(ids,composition='wide_finish')]},'rtl')
    panels=result[0]['panels']
    assert panels[-1]['box']['w']>=max(p['box']['w'] for p in panels[:-1])
    assert panels[-1]['box']['w']*panels[-1]['box']['h']>max(p['box']['w']*p['box']['h'] for p in panels[:-1])
    assert panels[-1]['box']['y']>max(p['box']['y']+p['box']['h'] for p in panels[:-1])


def test_failed_ai_repair_is_bounded_and_keeps_existing_layout(setup,monkeypatch):
    client,book,chapter=setup;store=client.app.state.store;calls=[]
    before=store.get('chapters',chapter['id'])
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('bad-'+str(len(calls)))
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':[page(['P2','P1'])]})])
    monkeypatch.setattr('mangastudio.page_flow.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/page-flow').json()['job_id']
    with pytest.raises(ValueError,match='zwei Korrekturen'):plan_page_flow(Worker(store),store.job(jobid))
    assert len(calls)==3 and store.get('chapters',chapter['id'])==before
    assert 'Erstes Pflichtpanel: P1' in calls[1]['2']['inputs']['prompt']
    assert 'Geliefert: P2, P1' in store.job(jobid)['payload']['flow_last_error']


@pytest.mark.parametrize('invalid',['skipped','turn','schema'])
def test_chunk_repair_explains_actual_error_and_preserves_finished_prefix(setup,monkeypatch,invalid):
    client,book,chapter=setup;store=client.app.state.store;before=store.get('chapters',chapter['id']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt=graph['2']['inputs']['prompt'];calls.append(prompt);kwargs['progress']('prefix-'+str(len(calls)))
            if len(calls)==1:
                return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':[page(['P1','P2','P3','P4'])]})])
            assert '"panel_count"' in prompt and '"maximum": 5' in prompt
            assert len(store.job(jobid)['payload']['completed_pages'])==1
            assert store.get('chapters',chapter['id'])==before
            if len(calls)==2:
                bad=page(['P5','P6','P7','P8'])
                if invalid=='skipped':bad['panels']=['P6','P7','P8']
                elif invalid=='turn':bad['turn']='reveal'
                else:bad['layout']='invented'
                return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':[bad]})])
            assert 'KONKRETER FEHLER:' in prompt
            if invalid=='skipped':assert 'Erstes Pflichtpanel: P5' in prompt
            elif invalid=='turn':assert 'braucht direkt davor eine Aufbau-Seite' in prompt
            else:assert 'pages.0.layout' in prompt and 'invented' not in prompt
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':[page(['P5','P6','P7','P8'])]})])
    monkeypatch.setattr('mangastudio.page_flow.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/page-flow').json()['job_id']
    plan_page_flow(Worker(store),store.job(jobid))
    assert len(calls)==3
    saved=store.get('chapters',chapter['id'])
    assert saved['scenes']==before['scenes'] and saved['revision']==before['revision']
    assert saved['page_flow_proposal']['status']=='pending'
    ids=[p['id'] for s in before['scenes'] for p in s['panels']]
    assert [pid for p in saved['page_flow_proposal']['plan']['pages'] for pid in p['panels']]==ids
    assert 'flow_last_error' not in store.job(jobid)['payload']


@pytest.mark.parametrize('composition',['wide_start','tall_start','wide_finish'])
@pytest.mark.parametrize('count',[2,3,4,5])
def test_emphasized_rectangles_are_largest_and_never_overlap(setup,composition,count):
    client,book,chapter=setup
    ids=[p['id'] for s in chapter['scenes'] for p in s['panels']][:count]
    boxes=[p['box'] for p in render_flow(chapter,{'pages':[page(ids,composition=composition)]},'rtl')[0]['panels']]
    hero=boxes[-1] if composition=='wide_finish' else boxes[0]
    assert hero['w']*hero['h']>=max(b['w']*b['h'] for b in boxes)
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            assert min(a['x']+a['w'],b['x']+b['w'])<=max(a['x'],b['x']) or min(a['y']+a['h'],b['y']+b['h'])<=max(a['y'],b['y'])


def test_timeout_resumes_same_remote_page_plan(setup,monkeypatch):
    client,book,chapter=setup;store=client.app.state.store;calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('known-flow')
            return SimpleNamespace(ok=False,error='COMFY_TIMEOUT: still running')
        def wait_for_prompt(self,prompt_id,**kwargs):
            assert prompt_id=='known-flow'
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':[
                page(['P1','P2','P3','P4']),page(['P5','P6','P7','P8'])]})])
    monkeypatch.setattr('mangastudio.page_flow.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/page-flow').json()['job_id']
    with pytest.raises(ValueError,match='COMFY_TIMEOUT'):plan_page_flow(Worker(store),store.job(jobid))
    plan_page_flow(Worker(store),store.job(jobid))
    assert len(calls)==1
    assert store.get('chapters',chapter['id'])['page_flow_proposal']['status']=='pending'


@pytest.mark.parametrize('bad_counts',[None,[8],[5,5],['4']])
def test_ai_counts_assign_panels_in_source_order_and_repair_invalid_counts(setup,monkeypatch,bad_counts):
    client,book,chapter=setup;store=client.app.state.store;before=store.get('chapters',chapter['id']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('count-'+str(len(calls)))
            counts=bad_counts if len(calls)==1 and bad_counts is not None else [4,4]
            pages=[]
            for count in counts:
                item=page([]);item.pop('panels');item['panel_count']=count;pages.append(item)
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'pages':pages})])
    monkeypatch.setattr('mangastudio.page_flow.ComfyClient',Client)
    jobid=client.post('/api/chapters/'+chapter['id']+'/page-flow').json()['job_id']
    plan_page_flow(Worker(store),store.job(jobid))
    saved=store.get('chapters',chapter['id'])
    assert saved['scenes']==before['scenes'] and saved['revision']==before['revision']
    ids=[p['id'] for s in before['scenes'] for p in s['panels']]
    proposed=saved['page_flow_proposal']['plan']['pages']
    assert [p['panels'] for p in proposed]==[ids[:4],ids[4:]]
    assert len(calls)==(1 if bad_counts is None else 2)
