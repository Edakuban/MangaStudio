import copy
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader
from mangastudio.models import Bubble
from mangastudio.lettering import panel_lettering
from mangastudio.layout import pages_for_chapter, page_geometry, BOX
from mangastudio.engine import Worker, image_signature
from mangastudio.layout_advice import suggest_layout
from mangastudio.web import create_app


def area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(poly, poly[1:]+poly[:1])))/2


def intersection(subject, clip):
    # Convex polygon clipping verifies actual silhouettes, not their overlapping boxes.
    orientation = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(clip, clip[1:]+clip[:1]))
    sign = 1 if orientation >= 0 else -1
    for a, b in zip(clip, clip[1:]+clip[:1]):
        result = []
        def cross(p): return sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
        for p, q in zip(subject, subject[1:]+subject[:1]):
            cp, cq = cross(p), cross(q)
            if cp >= -1e-8: result.append(p)
            if (cp >= 0) != (cq >= 0):
                t = cp/(cp-cq)
                result.append([p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])])
        subject = result
        if not subject: break
    return subject


@pytest.mark.parametrize('count', [2,3,4,5])
@pytest.mark.parametrize('direction', ['rtl','ltr'])
def test_diagonal_panels_do_not_overlap_or_leave_page(count, direction):
    geometry = page_geometry(count, 'dynamic', 0, 'normal', direction)
    assert len(geometry) == count
    for i, (box, poly) in enumerate(geometry):
        assert poly and area(poly) > 1000
        assert all(BOX[0] <= x <= BOX[0]+BOX[2]+.001 and BOX[1] <= y <= BOX[1]+BOX[3]+.001 for x,y in poly)
        for _, other in geometry[i+1:]:
            overlap = intersection(poly, other)
            assert not overlap or area(overlap) < .001


@pytest.mark.parametrize('shape', ['speech','thought','whisper','shout'])
def test_lettering_shapes_share_readable_geometry_and_hide_speaker_name(shape):
    panel = {'bubbles':[Bubble(text='Woher kommt das Licht?',speaker='Mara',shape=shape,
        x=.1,y=.1,width=.65,height=.3,tail_x=.7,tail_y=.8).model_dump()], 'caption':''}
    layout = panel_lettering(panel,300,350)
    bubble = layout['bubbles'][0]
    assert bubble['font_size'] == 10
    assert 'Mara' not in ' '.join(bubble['lines'])
    assert bubble['tail'] == [210,280]
    assert len(bubble['points']) >= 20
    assert not layout['issues']
    assert bool(bubble['thought_dots']) == (shape == 'thought')


def test_overflow_warns_without_shrinking_font_and_position_bounds_validate():
    b = Bubble(text='Ein langer Dialog mit vielen Wörtern. '*5, width=.2,height=.08,font_size=12)
    layout = panel_lettering({'bubbles':[b.model_dump()]},200,200)
    assert layout['issues'] and layout['bubbles'][0]['font_size'] == 12
    with pytest.raises(ValidationError): Bubble(text='Test', x=.9,width=.3)
    with pytest.raises(ValidationError): Bubble(text='Test', font_size=4)


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        project = client.post('/api/demo').json()
        book = client.get('/api/projects/'+project['id']).json()
        chapter = client.get('/api/chapters/'+book['chapters'][0]['id']).json()
        yield client, book, chapter


def test_preview_is_read_only_and_layout_controls_roundtrip(setup):
    client, book, chapter = setup
    store = client.app.state.store
    before = store.get('chapters',chapter['id'])
    scenes = copy.deepcopy(chapter['scenes'])
    scenes[0]['layout'] = 'dynamic'
    scenes[0]['panels'][0]['emphasis'] = 'normal'
    scenes[0]['panels'][0]['page_break_after'] = True
    scenes[0]['panels'][0]['bubbles'] = [Bubble(text='Hallo!',shape='shout',x=.1,y=.1,width=.7,height=.4).model_dump()]
    body = {'revision':chapter['revision'],'scenes':scenes}
    preview = client.post('/api/chapters/'+chapter['id']+'/preview',json=body)
    assert preview.status_code == 200, preview.text
    pages = preview.json()['pages']
    assert len(pages[0]['panels']) == 1
    assert pages[0]['panels'][0]['lettering']['bubbles'][0]['shape'] == 'shout'
    assert store.get('chapters',chapter['id']) == before
    saved = client.put('/api/chapters/'+chapter['id']+'/plan',json=body)
    assert saved.status_code == 200
    assert saved.json()['pages'] == pages


def test_final_pdf_rejects_text_overflow_while_draft_remains_reviewable(setup):
    from mangastudio.pdf_export import export_pdf
    client, book, chapter = setup
    store = client.app.state.store
    chapter['scenes'] = chapter['scenes'][:1]
    p = chapter['scenes'][0]['panels'][0]
    p['bubbles'] = [Bubble(text='Sehr langer Dialog '*10,width=.15,height=.08,font_size=18).model_dump()]
    target = store.root/'test.pdf'
    export_pdf(store,book,[chapter],target,draft=True)
    assert len(PdfReader(target).pages) == 1
    # Supply an existing image to get past the independent image-presence guard.
    from PIL import Image
    Image.new('RGB',(64,64),'gray').save(store.asset('test.png'))
    p['image'] = 'test.png'
    with pytest.raises(ValueError,match='Text passt'):
        export_pdf(store,book,[chapter],target,draft=False)


def test_ai_layout_job_preserves_story_images_and_resumes(setup,monkeypatch):
    client,book,chapter = setup
    store = client.app.state.store
    before = store.get('chapters',chapter['id'])
    calls = []
    class Client:
        def __init__(self,*args):pass
        def run_workflow(self,graph,**kwargs):
            prompt = graph['2']['inputs']['prompt']
            panels = json.loads(prompt.split('\nPANELS: ')[1].split('\nSCHEMA:')[0])
            calls.append(graph)
            kwargs['progress']('layout-'+str(len(calls)))
            return SimpleNamespace(ok=True,text_outputs=[json.dumps({'layout':'dynamic','rhythm':'action',
                'layout_reason':'Diagonale Teilung verstärkt die Bewegung.', 'panels':[{'panel':p['panel'],'beat':'action',
                'emphasis':'normal','border':'framed','page_break_before':False,'page_break_after':False} for p in panels]})])
    monkeypatch.setattr('mangastudio.layout_advice.ComfyClient',Client)
    result = client.post('/api/chapters/'+chapter['id']+'/layout')
    assert result.status_code == 200
    jobid = result.json()['job_id']
    suggest_layout(Worker(store),store.job(jobid))
    suggest_layout(Worker(store),store.job(jobid))
    assert len(calls) == len(before['scenes'])
    after = store.get('chapters',chapter['id'])
    for old_scene,new_scene in zip(before['scenes'],after['scenes']):
        assert new_scene['layout'] == 'dynamic'
        for old,new in zip(old_scene['panels'],new_scene['panels']):
            for key in ['id','description','visual_prompt','characters','bubbles','caption','image','image_signature']:
                assert new[key] == old[key]
            assert image_signature(book,new,book['characters'],store.settings()) == image_signature(book,old,book['characters'],store.settings())
