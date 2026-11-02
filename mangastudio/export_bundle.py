"""Atomic multi-format exports, sharing PDF lettering and a serialized PDFium renderer."""
import copy
from html import escape
from io import BytesIO
from pathlib import Path
import tempfile
import threading
from zipfile import ZipFile, ZIP_DEFLATED
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from .layout import book_pages, PAGE_W, PAGE_H
from .pdf_export import export_pdf, image_crop, draw_lettering, draw_text
from .print_quality import PAGE_WIDTH_MM, PAGE_HEIGHT_MM, PRINT_DPI
from .models import uid

# PDFium is not thread-safe, even with separate documents. All use lives here.
EXPORT_LOCK = threading.Lock()


def print_pdf(source, target, direction):
    """Convert reading order to a physical book block; preserve complete leaf pairs."""
    with open(source, 'rb') as stream:
        reader = PdfReader(stream)
        writer = PdfWriter()
        count = len(reader.pages)
        blank = count % 2
        first = reader.pages[0].mediabox
        if direction == 'rtl' and blank:
            writer.add_blank_page(width=float(first.width), height=float(first.height))
        indexes = range(count-1, -1, -1) if direction == 'rtl' else range(count)
        for index in indexes:
            writer.add_page(reader.pages[index])
        if direction != 'rtl' and blank:
            writer.add_blank_page(width=float(first.width), height=float(first.height))
        if reader.metadata:
            writer.add_metadata({k:v for k,v in reader.metadata.items() if isinstance(v,str)})
        with open(target, 'wb') as output:
            writer.write(output)
    return count + blank


def raster_pages(pdf_path):
    """Yield one PNG at a time, keeping memory bounded to the current page."""
    with pdfium.PdfDocument(str(pdf_path)) as document:
        for number in range(len(document)):
            page = document[number]
            try:
                bitmap = page.render(scale=PRINT_DPI/72)
                try:
                    image = bitmap.to_pil()
                    try:
                        stream = BytesIO()
                        image.save(stream, format='PNG', dpi=(PRINT_DPI, PRINT_DPI))
                        yield stream.getvalue()
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()


def strip_pdf(store, project, pages, target, draft):
    """One rectangular panel per PDF page; lettering keeps its physical dimensions."""
    c = canvas.Canvas(str(target), pageCompression=1)
    c.setTitle(project['title'])
    metadata = []
    sx, sy = PAGE_WIDTH_MM*mm/PAGE_W, PAGE_HEIGHT_MM*mm/PAGE_H
    for page in pages:
        for panel in page['panels']:
            w, h = panel['box']['w']*sx, panel['box']['h']*sy
            c.setPageSize((w,h))
            c.setFillColorRGB(1,1,1); c.rect(0,0,w,h,fill=1,stroke=0)
            if panel.get('image') and store.asset(panel['image']).is_file():
                c.drawImage(image_crop(store,panel,w,h,project['monochrome']),0,0,w,h)
            elif draft:
                draw_text(c, 'BILD FEHLT: '+panel['description'], 0,h,w,h,maximum=9)
            else:
                raise ValueError('Ein Panelbild fehlt für den Webcomic.')
            lettering = panel['lettering']
            if lettering['issues'] and not draft:
                raise ValueError(f'Panel {panel["order"]}: '+ ' '.join(lettering['issues']))
            draw_lettering(c,lettering,0,h)
            c.showPage()
            metadata.append({'chapter_id':page['chapter_id'],'chapter':page['chapter_title'],
                             'description':panel['description']})
    c.save()
    return metadata


def webcomic_zip(store, project, pages, target, workdir, draft):
    pdf_path=workdir/'webcomic-panels.pdf'
    metadata=strip_pdf(store,project,pages,pdf_path,draft)
    parts=[]; chapter=None
    with ZipFile(target,'w',compression=ZIP_DEFLATED) as archive:
        for index,(data,item) in enumerate(zip(raster_pages(pdf_path),metadata,strict=True),1):
            name=f'images/{index:04}.png'
            archive.writestr(name,data)
            if chapter!=item['chapter_id']:
                parts.append('<h2>'+escape(item['chapter'])+'</h2>');chapter=item['chapter_id']
            parts.append(f'<img src="{name}" alt="{escape(item["description"],quote=True)}" loading="lazy">')
        title=escape(project['title'])
        status='<p class="draft">LAYOUT-ENTWURF – kann fehlende Bilder enthalten</p>' if draft else ''
        html='<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>body{margin:0;background:#151719;color:#eee;font:18px/1.5 system-ui,sans-serif}main{max-width:900px;margin:auto;padding:24px 12px}h1,h2{text-align:center;overflow-wrap:anywhere}h2{margin:64px 0 24px}img{display:block;width:100%;height:auto;margin:0 auto 28px;background:white}.draft{text-align:center;color:#efc76b}</style></head><body><main><h1>'+title+'</h1>'+status+''.join(parts)+'</main></body></html>'
        archive.writestr('index.html',html)
        archive.writestr('README.txt','ZIP entpacken und index.html im Browser öffnen. Bilder liegen nummeriert unter images/. Leserichtung: von oben nach unten; Panelreihenfolge wie im Buch.\n')
    pdf_path.unlink()
    return len(metadata)


def create_exports(store, project, chapters, formats, draft=False):
    """Caller holds EXPORT_LOCK. Publish the directory only after all formats succeed."""
    formats=list(dict.fromkeys(formats))
    if 'grayscale' in formats and project['monochrome']:
        raise ValueError('Das Buch ist bereits auf Schwarzweiß gestellt. Für diese Ausgabe genügt PDF.')
    pages=book_pages(chapters,project['direction'])
    if not pages: raise ValueError('Es gibt noch kein Storyboard für den Export.')
    relative=f'books/{project["id"]}/exports/{uid()}'
    parent=store.asset(relative).parent; parent.mkdir(parents=True,exist_ok=True)
    prefix='entwurf' if draft else 'manga'
    files=[]
    with tempfile.TemporaryDirectory(prefix='.export-',dir=parent) as temp:
        work=Path(temp); publish=work/'ready';publish.mkdir()
        def add(kind,name,label,count):
            files.append({'kind':kind,'path':relative+'/'+name,'name':name,'label':label,'count':count})
        pdf=work/'pages.pdf'
        total=export_pdf(store,project,chapters,pdf,draft)
        if 'pdf' in formats or 'pages' in formats:
            if 'pdf' in formats:
                name=prefix+'.pdf';(publish/name).write_bytes(pdf.read_bytes());add('pdf',name,'Lese-PDF',total)
            if 'pages' in formats:
                name=prefix+'-seiten.zip'
                with ZipFile(publish/name,'w',compression=ZIP_DEFLATED) as archive:
                    for index,data in enumerate(raster_pages(pdf),1): archive.writestr(f'{index:04}.png',data)
                add('pages',name,'Seitenbilder (PNG, 300 dpi)',total)
        if 'print_pdf' in formats:
            name=prefix+'-druck.pdf'
            count=print_pdf(pdf,publish/name,project['direction'])
            label='Druck-PDF · umgekehrte Seitenfolge' if project['direction']=='rtl' else 'Druck-PDF'
            add('print_pdf',name,label,count)
        if 'grayscale' in formats:
            mono=copy.deepcopy(project);mono['monochrome']=True
            name=prefix+'-graustufen.pdf';export_pdf(store,mono,chapters,publish/name,draft)
            add('grayscale',name,'Graustufen-PDF',total)
        if 'webcomic' in formats:
            name=prefix+'-webcomic.zip'
            count=webcomic_zip(store,project,pages,publish/name,work,draft)
            add('webcomic',name,'Webcomic (HTML + Panelbilder)',count)
        if len(files)>1:
            download=prefix+'-exportpaket.zip'
            with ZipFile(publish/download,'w',compression=ZIP_DEFLATED) as archive:
                for item in files: archive.write(publish/item['name'],item['name'])
        else: download=files[0]['name']
        publish.replace(store.asset(relative))
    return {'path':relative+'/'+download,'name':download,'pages':total,'draft':draft,'files':files}
