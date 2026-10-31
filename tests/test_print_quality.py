import math
from types import SimpleNamespace
import pytest
from PIL import Image
from pypdf import PdfReader
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.engine import Worker,image_signature
from mangastudio.layout import pages_for_chapter,PAGE_W,PAGE_H
from mangastudio.print_quality import panel_pixel_size,image_is_print_ready
from mangastudio.pdf_export import export_pdf


@pytest.mark.parametrize('w,h',[(1000,1420),(904,1240),(440,600),(1000,150),(180,1420),(410.3,311.7)])
def test_native_size_meets_300_dpi_and_model_grid(w,h):
    width,height=panel_pixel_size({'w':w,'h':h})
    assert width%16==0 and height%16==0
    assert width/(w/PAGE_W*176/25.4)>=300
    assert height/(h/PAGE_H*250/25.4)>=300
    if w==1000 and h==1420:assert (width,height)==(2080,2960)


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        project=client.post('/api/demo').json()
        chapter=client.app.state.store.list('chapters',project['id'])[0]
        chapter['scenes']=chapter['scenes'][:1]
        panel=chapter['scenes'][0]['panels'][0];panel['caption']='';panel['bubbles']=[]
        client.app.state.store.write('chapters',chapter,project['id'],chapter['position'])
        yield client,client.app.state.store,project,chapter


def test_low_resolution_is_regenerated_missing_only_skips_ready_images_and_reflow_is_rechecked(setup,monkeypatch):
    client,store,book,chapter=setup;panel=chapter['scenes'][0]['panels'][0];pid=panel['id']
    panel['image']='old.png';Image.new('RGB',(752,1024),'gray').save(store.asset('old.png'))
    panel['image_signature']=image_signature(book,panel,store.list('characters',book['id']),store.settings())
    store.write('chapters',chapter,book['id'],chapter['position']);calls=[]
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            calls.append(graph);kwargs['progress']('hires');return SimpleNamespace(ok=True,output_files=['out.png'])
        def download_output(self,filename,path):
            size=calls[-1]['7']['inputs'];path.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(size['width'],size['height']),'gray').save(path)
    monkeypatch.setattr('mangastudio.engine.ComfyClient',Client)
    assert pid in client.get('/api/chapters/'+chapter['id']).json()['stale_panels']
    job=store.enqueue(book['id'],chapter['id'],'images',{'panel_id':pid,'missing_only':True})
    Worker(store).images(store.job(job));store.update_job(job,state='done')
    saved=store.get('chapters',chapter['id']);p=saved['scenes'][0]['panels'][0]
    box=pages_for_chapter(saved,book['direction'])[0]['panels'][0]['box']
    assert image_is_print_ready(store,p,box) and store.asset('old.png').exists()
    assert pid not in client.get('/api/chapters/'+chapter['id']).json()['stale_panels']
    job=store.enqueue(book['id'],chapter['id'],'images',{'panel_id':pid,'missing_only':True})
    Worker(store).images(store.job(job));store.update_job(job,state='done');assert len(calls)==1
    saved['scenes'][0]['layout']='full_bleed'
    store.write('chapters',saved,book['id'],saved['position'])
    assert pid in client.get('/api/chapters/'+chapter['id']).json()['stale_panels']


def test_export_embeds_at_least_300_ppi_at_actual_b5_size(setup,tmp_path):
    client,store,book,chapter=setup
    chapter['scenes'][0]['layout']='full_bleed'
    p=chapter['scenes'][0]['panels'][0];p['image']='full.png'
    Image.new('RGB',(2080,2960),'gray').save(store.asset(p['image']))
    pdf=tmp_path/'300dpi.pdf';assert export_pdf(store,book,[chapter],pdf,draft=False)==1
    page=PdfReader(pdf).pages[0];objects=page['/Resources']['/XObject'].get_object();placements=[]
    def visit(op,args,ctm,tm):
        if op!=b'Do':return
        image=objects[args[0]].get_object()
        if image.get('/Subtype')!='/Image':return
        placements.append((image['/Width']*72/math.hypot(ctm[0],ctm[1]),image['/Height']*72/math.hypot(ctm[2],ctm[3])))
    page.extract_text(visitor_operand_before=visit)
    assert len(placements)==1
    assert all(value>=300 for value in placements[0])


def test_final_export_rejects_insufficient_native_pixels_but_draft_remains_available(setup):
    from mangastudio.models import Scene,Panel
    client,store,_,_=setup
    book=client.post('/api/import',files={'file':('single.txt',b'A single documented moment in a quiet courtyard.')}).json()
    ch=store.list('chapters',book['id'])[0]
    p=Panel(description='Eine ruhige Aufnahme.',visual_prompt='A quiet courtyard.',image='tiny.png').model_dump()
    Image.new('RGB',(256,256),'gray').save(store.asset(p['image']))
    p['image_signature']=image_signature(book,p,[],store.settings())
    ch['scenes']=[Scene(title='Aufnahme',source_start=1,source_end=1,source_excerpt=ch['text'],panels=[Panel.model_validate(p)]).model_dump()]
    store.write('chapters',ch,book['id'],ch['position'])
    result=client.post('/api/projects/'+book['id']+'/export',json={'draft':False})
    assert result.status_code==400 and '300 dpi' in result.json()['detail']
    result=client.post('/api/projects/'+book['id']+'/export',json={'draft':True})
    assert result.status_code==200,result.text
