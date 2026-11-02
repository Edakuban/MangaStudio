from io import BytesIO
from zipfile import ZipFile
import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader
from fastapi.testclient import TestClient
from mangastudio.web import create_app
from mangastudio.models import Panel, Scene
from mangastudio.engine import image_signature
from mangastudio.export_bundle import EXPORT_LOCK, raster_pages


@pytest.fixture
def book(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        store=client.app.state.store
        project=client.post('/api/import',files={'file':('test.txt',b'A traveler enters the courtyard. Then the traveler opens a book.')}).json()
        project['monochrome']=False;project['title']='Test <script> & Farbe';store.write('projects',project)
        chapter=store.list('chapters',project['id'])[0]
        panels=[]
        for index,color in enumerate(['red','blue']):
            panel=Panel(description=f'Action {index} <look>',visual_prompt=f'Courtyard moment {index}',image=f'color-{index}.png',bubbles=[{'text':f'Hallo {index}'}]).model_dump()
            Image.new('RGB',(2080,2960),color).save(store.asset(panel['image']))
            panel['image_signature']=image_signature(project,panel,[],store.settings())
            panels.append(Panel.model_validate(panel))
        chapter['scenes']=[Scene(title='Hof',source_start=1,source_end=1,source_excerpt=chapter['text'],layout='balanced',panels=panels).model_dump()]
        store.write('chapters',chapter,project['id'],chapter['position'])
        yield client,store,project,chapter


def test_all_formats_share_page_count_preserve_colors_and_provide_offline_vertical_comic(book):
    client,store,project,chapter=book
    response=client.post('/api/projects/'+project['id']+'/export',json={'formats':['pdf','grayscale','pages','webcomic']})
    assert response.status_code==200,response.text
    result=response.json();files={x['kind']:x for x in result['files']}
    assert set(files)=={'pdf','grayscale','pages','webcomic'}
    for item in [result,*files.values()]:
        assert client.get('/assets/'+item['path']).status_code==200
    assert len(PdfReader(store.asset(files['pdf']['path'])).pages)==result['pages']
    gray=PdfReader(store.asset(files['grayscale']['path']))
    for page in gray.pages:
        images=page['/Resources']['/XObject'].get_object().values()
        assert all(x.get_object()['/ColorSpace']=='/DeviceGray' for x in images)
    with ZipFile(store.asset(files['pages']['path'])) as archive:
        assert archive.namelist()==[f'{i:04}.png' for i in range(1,result['pages']+1)]
        image=Image.open(BytesIO(archive.read('0001.png')))
        assert image.width>=2078 and image.height>=2952
        assert abs(image.info['dpi'][0]-300)<1
        r,g,b=image.convert('RGB').split()
        assert ImageChops.difference(r,g).getbbox() # Original export stays colored.
    with ZipFile(store.asset(files['webcomic']['path'])) as archive:
        assert 'images/0001.png' in archive.namelist() and 'images/0002.png' in archive.namelist()
        html=archive.read('index.html').decode()
        assert '<script>' not in html and '&lt;script&gt;' in html
        assert html.index('images/0001.png')<html.index('images/0002.png')
        assert 'src="http' not in html
        first=Image.open(BytesIO(archive.read('images/0001.png'))).convert('RGB')
        second=Image.open(BytesIO(archive.read('images/0002.png'))).convert('RGB')
        assert first.getpixel((first.width//2,first.height//2))==(255,0,0)
        assert second.getpixel((second.width//2,second.height//2))==(0,0,255)
        # White dialogue bubble is baked into the PNG, not only an HTML overlay.
        assert first.getextrema()[0][0]<30 and first.getextrema()[1][1]==255
    with ZipFile(store.asset(result['path'])) as archive:
        assert set(archive.namelist())=={f['name'] for f in files.values()}
    assert store.get('projects',project['id'])['monochrome'] is False
    assert store.get('chapters',chapter['id'])==chapter


def test_export_validation_and_serialized_renderer(book):
    client,store,project,chapter=book;url='/api/projects/'+project['id']+'/export'
    for formats in [[],['unknown']]: assert client.post(url,json={'formats':formats}).status_code==422
    EXPORT_LOCK.acquire()
    try: assert client.post(url,json={'formats':['pages']}).status_code==409
    finally: EXPORT_LOCK.release()
    project['monochrome']=True;store.write('projects',project)
    assert client.post(url,json={'draft':True,'formats':['grayscale']}).status_code==400
    chapter['scenes'][0]['panels'][0]['image']=''
    store.write('chapters',chapter,project['id'],chapter['position'])
    assert client.post(url,json={'formats':['webcomic']}).status_code==400
    draft=client.post(url,json={'draft':True,'formats':['webcomic']})
    assert draft.status_code==200,draft.text
    with ZipFile(store.asset(draft.json()['path'])) as archive:
        assert 'LAYOUT-ENTWURF' in archive.read('index.html').decode()


def test_failed_variant_publishes_no_partial_files_or_history(book,monkeypatch):
    client,store,project,_=book
    def fail(*args,**kwargs): raise ValueError('Synthetic rendering failure')
    monkeypatch.setattr('mangastudio.export_bundle.webcomic_zip',fail)
    response=client.post('/api/projects/'+project['id']+'/export',json={'formats':['pdf','webcomic']})
    assert response.status_code==400
    assert not store.get('projects',project['id']).get('exports')
    assert list(store.asset(f'books/{project["id"]}/exports').iterdir())==[]
    assert not EXPORT_LOCK.locked()


@pytest.mark.parametrize('direction',['rtl','ltr'])
@pytest.mark.parametrize('page_count',[2,3])
def test_print_book_block_preserves_pairs_and_reading_pdf(book,direction,page_count):
    client,store,project,chapter=book
    project['direction']=direction;store.write('projects',project)
    panels=chapter['scenes'][0]['panels']
    if page_count==3:
        panels.append(Panel(description='Third',visual_prompt='Third',image=panels[0]['image'],
                            bubbles=[{'text':'Hallo 2'}]).model_dump())
    for panel in panels: panel['emphasis']='splash'
    store.write('chapters',chapter,project['id'],chapter['position'])
    response=client.post('/api/projects/'+project['id']+'/export',json={'draft':True,'formats':['pdf','print_pdf']})
    assert response.status_code==200,response.text
    result=response.json();files={f['kind']:f for f in result['files']}
    reading=PdfReader(store.asset(files['pdf']['path']))
    printed=PdfReader(store.asset(files['print_pdf']['path']))
    assert len(reading.pages)==page_count
    assert len(printed.pages)==files['print_pdf']['count']==page_count+page_count%2
    expected=[f'Hallo {i}' for i in range(page_count)]
    assert all(text in page.extract_text() for text,page in zip(expected,reading.pages))
    physical=[page.extract_text() for page in printed.pages]
    if page_count%2:
        assert physical[0 if direction=='rtl' else -1]==''
        physical=physical[1:] if direction=='rtl' else physical[:-1]
    if direction=='rtl': expected.reverse()
    assert all(text in page for text,page in zip(expected,physical))
    root=reading.trailer['/Root']
    assert root['/ViewerPreferences']['/Direction']==('/R2L' if direction=='rtl' else '/L2R')
    assert root['/PageLayout']==('/TwoPageLeft' if direction=='rtl' else '/TwoPageRight')
    # Physical print order must not inherit digital RTL spread instructions.
    assert '/ViewerPreferences' not in printed.trailer['/Root']
    assert '/PageLayout' not in printed.trailer['/Root']
    assert store.get('chapters',chapter['id'])==chapter


def test_standard_pages_precede_story_and_reverse_with_complete_block(book):
    client,store,project,chapter=book
    url='/api/projects/'+project['id']
    settings={'enabled':True,'title':'Samuel Hellsworth','subtitle':'Band I · Spuren des Hochmuts',
              'author':'Ed Berg','imprint':'Impressum\n\nCopyright Testausgabe\nISBN: Beispiel'}
    assert client.put(url+'/publication',json=settings).status_code==200
    response=client.post(url+'/export',json={'draft':True,'formats':['pdf','print_pdf','grayscale']})
    assert response.status_code==200,response.text
    result=response.json();files={f['kind']:f for f in result['files']}
    reading=PdfReader(store.asset(files['pdf']['path']))
    assert result['pages']==files['pdf']['count']==5
    texts=[p.extract_text() for p in reading.pages]
    assert 'Samuel Hellsworth' in texts[0] and 'Ed Berg' in texts[0]
    assert texts[1]==''
    assert 'Band I' in texts[2]
    assert 'Impressum' in texts[3] and 'ISBN: Beispiel' in texts[3]
    assert 'Hallo 0' in texts[4] and '05' in texts[4]
    printed=PdfReader(store.asset(files['print_pdf']['path']))
    assert files['print_pdf']['count']==6
    assert [p.extract_text() for p in printed.pages]==['']+texts[::-1]
    assert [p.extract_text() for p in PdfReader(store.asset(files['grayscale']['path'])).pages]==texts
    assert store.get('chapters',chapter['id'])==chapter


def test_cover_upload_survives_settings_save_and_is_optional(book):
    client,store,project,_=book;url='/api/projects/'+project['id']
    data=BytesIO();Image.new('RGB',(2200,3100),'green').save(data,format='PNG')
    upload=client.post(url+'/publication/cover',files={'file':('cover.png',data.getvalue(),'image/png')})
    assert upload.status_code==200,upload.text
    path=upload.json()['cover_image']
    saved=client.put(url+'/publication',json={'enabled':True,'imprint':'Impressum'})
    assert saved.json()['cover_image']==path
    response=client.post(url+'/export',json={'formats':['pdf','grayscale']})
    assert response.status_code==200,response.text
    files={f['kind']:f for f in response.json()['files']}
    cover=PdfReader(store.asset(files['pdf']['path'])).pages[0]
    assert cover.extract_text()==''
    assert '/XObject' in cover['/Resources']
    gray=PdfReader(store.asset(files['grayscale']['path'])).pages[0]
    assert all(x.get_object()['/ColorSpace']=='/DeviceGray' for x in gray['/Resources']['/XObject'].get_object().values())
    small=BytesIO();Image.new('RGB',(100,150),'red').save(small,format='PNG')
    assert client.post(url+'/publication/cover',files={'file':('small.png',small.getvalue(),'image/png')}).status_code==200
    rejected=client.post(url+'/export',json={'formats':['pdf']})
    assert rejected.status_code==400 and '300 dpi' in rejected.text
    assert client.post(url+'/export',json={'draft':True}).status_code==200
    assert client.delete(url+'/publication/cover').status_code==200
    assert not store.get('projects',project['id'])['publication'].get('cover_image')
    assert store.asset(path).is_file()  # Removing the reference keeps the recoverable file.
    assert client.put(url+'/publication',json={'enabled':True,'cover_image':'../bad'}).status_code==422


def test_standard_page_overflow_and_missing_imprint_do_not_publish(book):
    client,store,project,_=book;url='/api/projects/'+project['id']
    for imprint in ('','Line\n'*100):
        assert client.put(url+'/publication',json={'enabled':True,'imprint':imprint}).status_code==200
        response=client.post(url+'/export',json={'draft':True})
        assert response.status_code==400,response.text
        assert not store.get('projects',project['id']).get('exports')
    assert client.put(url+'/publication',json={'enabled':False}).status_code==200
    assert client.post(url+'/export',json={'draft':True}).status_code==200
