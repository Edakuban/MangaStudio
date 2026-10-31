from io import BytesIO
import json
import zipfile
import pytest
from PIL import Image
from pypdf import PdfReader
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.models import PlanChunk, Scene, Panel, Bubble, uid
from mangastudio.layout import layout_boxes, book_pages, BOX
from mangastudio.engine import validate_chunk, image_graph, Worker, decode_plan, planner_schema
from mangastudio.importer import chunks
from mangastudio.models import Settings


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'data', start_worker=False)
    with TestClient(app) as c:
        yield c


def demo(client):
    book = client.post('/api/demo').json()
    project = client.get('/api/projects/'+book['id']).json()
    chapter = client.get('/api/chapters/'+project['chapters'][0]['id']).json()
    return project, chapter


def test_dialog_vertical_position_roundtrip_and_legacy_default(client):
    assert Bubble(text='Altbestand').vertical == 'top'
    project, chapter = demo(client)
    chapter['scenes'][0]['panels'][0]['bubbles'] = [
        {'text': 'Oben rechts', 'side': 'right'},
        {'text': 'Unten links', 'side': 'left', 'vertical': 'bottom'}]
    saved = client.put('/api/chapters/'+chapter['id']+'/plan', json={
        'revision': chapter['revision'], 'scenes': chapter['scenes']})
    assert saved.status_code == 200, saved.text
    bubbles = client.get('/api/chapters/'+chapter['id']).json()['scenes'][0]['panels'][0]['bubbles']
    assert [b['vertical'] for b in bubbles] == ['top', 'bottom']


@pytest.mark.parametrize('positions', [('top', 'top'), ('top', 'bottom'), ('bottom', 'bottom')])
def test_pdf_vertical_dialogs_keep_order_and_clear_caption(client, tmp_path, monkeypatch, positions):
    from mangastudio import pdf_export as pdf
    project, chapter = demo(client)
    chapter['scenes'] = chapter['scenes'][:1]
    panel = chapter['scenes'][0]['panels'][0]
    chapter['scenes'][0]['panels'] = [panel]
    panel['emphasis'] = 'splash'
    panel['caption'] = 'Erzählkasten unten.'
    panel['bubbles'] = [{'text': 'Dialog eins', 'side': 'left', 'vertical': positions[0]},
                        {'text': 'Dialog zwei', 'side': 'right', 'vertical': positions[1]}]
    recorded = {}
    original = pdf.draw_lettering
    def track(c, lettering, x, top):
        for b in lettering['bubbles']:
            recorded[' '.join(b['lines'])] = (x+b['x'], top-b['y'], top-b['y']-b['height'])
        cap = lettering['caption']
        recorded[' '.join(cap['lines'])] = (x+cap['x'], top-cap['y'], top-cap['y']-cap['height'])
        return original(c, lettering, x, top)
    monkeypatch.setattr(pdf, 'draw_lettering', track)
    target = tmp_path/'dialog.pdf'
    pdf.export_pdf(client.app.state.store, project, [chapter], target, draft=True)
    one, two, caption = (recorded[t] for t in ['Dialog eins', 'Dialog zwei', 'Erzählkasten unten.'])
    assert one[0] < two[0]  # Horizontal setting remains independent.
    assert one[2] > two[1]  # First dialogue above the second; no overlap.
    assert two[2] > caption[1]  # Both stay clear of the bottom caption.
    assert 'Dialog zwei' in PdfReader(target).pages[0].extract_text()


def test_import_docx_and_txt(client):
    text = 'Kapitel 1\n\nEin richtiger Anfang.\n\nKapitel 2\n\nDie Geschichte geht weiter.'
    res = client.post('/api/import', files={'file': ('roman.txt', text.encode(), 'text/plain')})
    assert res.status_code == 200
    book = client.get('/api/projects/'+res.json()['id']).json()
    assert len(book['chapters']) == 2
    contents = {'[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
                '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
                'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Kapitel 1</w:t></w:r></w:p><w:p><w:r><w:t>Eine Geschichte beginnt hier.</w:t></w:r></w:p></w:body></w:document>'}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for name, value in contents.items():
            z.writestr(name, value)
    res = client.post('/api/import', files={'file': ('roman.docx', buffer.getvalue(), 'application/octet-stream')})
    assert res.status_code == 200, res.text
    assert client.post('/api/import', files={'file': ('bad.docx', b'not a zip')}).status_code == 400


def test_planner_omits_blank_dialogue_placeholders_without_changing_real_dialogue():
    raw = {'summary': 'Stille und Dialog', 'scenes': [{'title': 'Szene', 'source_start': 1, 'source_end': 1,
        'source_excerpt': 'Eine Szene in der Nacht.', 'panels': [
            {'description': 'Stille', 'visual_prompt': 'A silent street', 'bubbles': [{'text': ''}, {'text': ' \n\t '}]},
            {'description': 'Dialog', 'visual_prompt': 'A man speaking', 'bubbles': [
                {'text': '', 'speaker': 'Sam'}, {'text': 'Wer ist da?', 'speaker': 'Sam', 'side': 'left', 'vertical': 'bottom'}]}]}]}
    panels = decode_plan(json.dumps(raw)).scenes[0].panels
    assert panels[0].bubbles == []
    assert len(panels[1].bubbles) == 1
    assert panels[1].bubbles[0].model_dump(include={'text','speaker','side','vertical'}) == {'text': 'Wer ist da?', 'speaker': 'Sam', 'side': 'left', 'vertical': 'bottom'}


@pytest.mark.parametrize('bubble', [{'text': None}, {'speaker': 'Sam'}, {'text': 42}])
def test_planner_keeps_invalid_dialogue_errors(bubble):
    from pydantic import ValidationError
    raw = {'summary': 'Test', 'scenes': [{'title': 'Szene', 'source_start': 1, 'source_end': 1,
        'source_excerpt': 'Eine Szene in der Nacht.', 'panels': [
            {'description': 'Dialog', 'visual_prompt': 'A man speaking', 'bubbles': [bubble]}]}]}
    with pytest.raises(ValidationError):
        decode_plan(json.dumps(raw))


@pytest.mark.parametrize('count', range(1, 6))
@pytest.mark.parametrize('variant', [0, 1])
@pytest.mark.parametrize('direction', ['rtl', 'ltr'])
def test_layout_stays_in_bounds_and_nonoverlapping(count, variant, direction):
    boxes = layout_boxes(count, variant, 'normal', direction)
    x, y, w, h = BOX
    for box in boxes:
        assert x-.001 <= box['x'] and y-.001 <= box['y']
        assert box['x']+box['w'] <= x+w+.001
        assert box['y']+box['h'] <= y+h+.001
        assert box['w'] > 50 and box['h'] > 50
    for i, a in enumerate(boxes):
        for b in boxes[i+1:]:
            overlap = min(a['x']+a['w'], b['x']+b['w'])-max(a['x'], b['x'])
            overlap_y = min(a['y']+a['h'], b['y']+b['h'])-max(a['y'], b['y'])
            assert overlap <= 0 or overlap_y <= 0


def test_dynamic_demo_pdf_and_export_guards(client):
    project, chapter = demo(client)
    assert len(chapter['scenes']) == 3
    assert [len(p['panels']) for p in chapter['pages']] == [1, 4, 3]
    assert client.post('/api/projects/'+project['id']+'/export', json={'draft': False}).status_code == 400
    result = client.post('/api/projects/'+project['id']+'/export', json={'draft': True})
    assert result.status_code == 200, result.text
    pdf = client.get('/assets/'+result.json()['path']).content
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 6
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert 'Mara' in text and 'LAYOUT-ENTWURF' in text
    assert float(reader.pages[0].mediabox.width) == pytest.approx(176*72/25.4, abs=.01)


def test_edit_revision_source_and_paths(client):
    project, chapter = demo(client)
    bad = json.loads(json.dumps(chapter['scenes']))
    bad[0]['source_excerpt'] = 'Dieser Text wurde erfunden und ist nicht im Buch.'
    assert client.put(f'/api/chapters/{chapter["id"]}/plan', json={'revision': chapter['revision'], 'scenes': bad}).status_code == 400
    changes = {'revision': chapter['revision'], 'scenes': chapter['scenes']}
    changes['scenes'][0]['panels'][0]['caption'] = 'Überarbeitete Erzählung.'
    res = client.put(f'/api/chapters/{chapter["id"]}/plan', json=changes)
    assert res.status_code == 200, res.text
    assert client.put(f'/api/chapters/{chapter["id"]}/plan', json=changes).status_code == 409
    assert client.get('/assets/manga.sqlite3').status_code == 404
    assert client.post('/api/demo', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_clear_chapter_storyboard_preserves_source_and_other_chapters(client):
    project, chapter = demo(client)
    store = client.app.state.store
    before = store.get('chapters', chapter['id'])
    others = [c for c in store.list('chapters', project['id']) if c['id'] != chapter['id']]
    result = client.put('/api/chapters/'+chapter['id']+'/plan', json={'revision': chapter['revision'], 'scenes': []})
    assert result.status_code == 200, result.text
    assert result.json()['scenes'] == [] and result.json()['pages'] == []
    current = store.get('chapters', chapter['id'])
    assert current['summary'] == '' and current['text'] == before['text']
    assert current['revision'] == before['revision']+1
    assert [c for c in store.list('chapters', project['id']) if c['id'] != chapter['id']] == others


def test_character_panel_upload_and_staleness(client):
    project, chapter = demo(client)
    buffer = BytesIO()
    Image.new('RGB', (2000, 3000), '#ddd').save(buffer, 'PNG')
    res = client.post(f'/api/projects/{project["id"]}/characters', data={'name': 'Juna', 'description': 'Kurzes Haar, 30 Jahre.'}, files={'file': ('ref.png', buffer.getvalue(), 'image/png')})
    assert res.status_code == 200, res.text
    assert client.get('/assets/'+res.json()['image']).status_code == 200
    panel_id = chapter['scenes'][0]['panels'][0]['id']
    res = client.post(f'/api/chapters/{chapter["id"]}/panels/{panel_id}/image', files={'file': ('panel.png', buffer.getvalue(), 'image/png')})
    assert res.status_code == 200, res.text
    assert panel_id not in res.json()['stale_panels']
    changes = {'revision': res.json()['revision'], 'scenes': res.json()['scenes']}
    changes['scenes'][0]['panels'][0]['visual_prompt'] += ' New composition.'
    res = client.put(f'/api/chapters/{chapter["id"]}/plan', json=changes)
    assert panel_id in res.json()['stale_panels']


def test_chunks_never_drop_text_and_source_validation():
    original = ' '.join('word'+str(i) for i in range(12000))
    parts = chunks(original)
    assert ' '.join(text for part in parts for _, text in part) == original
    result = PlanChunk(summary='x', scenes=[Scene(title='Szene', source_start=1, source_end=1,
                source_excerpt='Der Bahnhof war leer.', panels=[Panel(description='Leer', visual_prompt='Empty train station')])])
    validate_chunk(result, [(1, 'Der Bahnhof war leer. Dann kam Mara.')], set())
    result.scenes[0].source_excerpt = 'Nichts davon stand hier.'
    with pytest.raises(ValueError):
        validate_chunk(result, [(1, 'Der Bahnhof war leer.')], set())


def test_reference_graph_and_safe_job_retry(client):
    graph = image_graph(Settings(), 'A manga panel', ['cast/a.png', 'cast/b.png'], 1024, 768, 42)
    assert sum(n['class_type']=='ReferenceLatent' for n in graph.values()) == 4
    assert graph['6']['inputs']['positive'][0] == '28'
    project, chapter = demo(client)
    result = client.post('/api/chapters/'+chapter['id']+'/images', json={})
    assert result.status_code == 200
    job_id = result.json()['job_id']
    assert client.post('/api/chapters/'+chapter['id']+'/images', json={}).status_code == 400
    assert client.put('/api/chapters/'+chapter['id']+'/plan', json={'revision': chapter['revision'], 'scenes': chapter['scenes']}).status_code == 409
    store = client.app.state.store
    store.update_job(job_id, state='failed', payload={'remote': {'operation':'image:test', 'prompt_id':'known'}})
    assert client.post('/api/jobs/'+job_id+'/retry').status_code == 200
    assert store.job(job_id)['payload']['remote']['prompt_id'] == 'known'


def test_resume_uses_existing_prompt(client):
    project, chapter = demo(client)
    store = client.app.state.store
    job_id = store.enqueue(project['id'], chapter['id'], 'images', {'remote': {'operation': 'image:test', 'prompt_id': 'old-id'}})
    job = store.job(job_id)
    class Client:
        def wait_for_prompt(self, prompt_id, **kwargs):
            assert prompt_id == 'old-id'
            return type('Result', (), {'ok': True})()
        def run_workflow(self, *args, **kwargs):
            raise AssertionError('Must not resubmit')
    assert Worker(store).run(job, {}, 'image:test', Client(), Settings()).ok


def test_llm_ids_and_paths_are_never_trusted():
    raw = {'summary': 'Eine Szene.', 'scenes': [{'id': 'example-id', 'title': 'Ankunft',
        'source_start': 1, 'source_end': 1, 'source_excerpt': 'Der Bahnhof war leer.',
        'panels': [{'id': '../../escape', 'image': '../manga.sqlite3', 'description': 'Ankunft',
                    'visual_prompt': 'An empty station'}]}]}
    result = decode_plan(json.dumps(raw))
    assert len(result.scenes[0].id) == 32
    assert result.scenes[0].panels[0].image == ''
    assert 'id' not in planner_schema()['$defs']['Scene']['properties']


def test_source_preview_is_copied_from_original_not_from_model():
    evidence = ' '.join('Originalwort'+str(i) for i in range(95))
    raw = {'summary': 'Eine Szene.', 'scenes': [{'id': 'a1b2c3-not-an-id', 'title': 'Ankunft',
        'source_start': 1, 'source_end': 1, 'source_excerpt': evidence,
        'panels': [{'description': 'Ankunft', 'visual_prompt': 'Empty station'}]}]}
    result = decode_plan(json.dumps(raw), [], [(1, evidence)])
    assert 8 <= len(result.scenes[0].source_excerpt) <= 240
    validate_chunk(result, [(1, evidence)], set())
    raw['scenes'][0]['source_excerpt'] = evidence+' Dieses Ende ist erfunden.'
    normalized = decode_plan(json.dumps(raw), [], [(1, evidence)])
    assert normalized.scenes[0].source_excerpt == result.scenes[0].source_excerpt
    assert normalized.scenes[0].source_excerpt in evidence
    raw['scenes'][0]['source_end'] = 99999
    with pytest.raises(ValueError, match='Quellabsätze'):
        decode_plan(json.dumps(raw), [], [(1, evidence)])
    schema = planner_schema()['$defs']['Scene']
    assert 'source_excerpt' not in schema['properties']
    assert 'source_excerpt' not in schema['required']
