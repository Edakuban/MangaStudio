"""Optional four-page front matter, counted in reading order before print reversal."""
from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from .models import PublicationSettings
from .lettering import FONT


def publication_count(project):
    return 4 if project.get('publication', {}).get('enabled') else 0


def text_lines(text, size, width):
    from .pdf_export import lines_for
    return [line for paragraph in text.split('\n') for line in (lines_for(paragraph,size,width) if paragraph.strip() else [''])]


def draw_block(c, text, size, x, top, width, height, centered=False):
    lines = text_lines(text,size,width)
    if len(lines)*size*1.4 > height:
        raise ValueError('Standardseiten: Text ist zu lang für eine Seite. Bitte kürzen.')
    c.setFillColorRGB(0,0,0)
    c.setFont(FONT,size)
    for i,line in enumerate(lines):
        y=top-size-i*size*1.4
        if centered: c.drawCentredString(x+width/2,y,line)
        else: c.drawString(x,y,line)


def draw_publication(c, store, project, width, height, draft):
    if not publication_count(project): return
    raw=project['publication']
    settings=PublicationSettings.model_validate({k:v for k,v in raw.items() if k!='cover_image'})
    if not settings.imprint.strip():
        raise ValueError('Bitte das Impressum für Seite 4 ausfüllen oder Standardseiten deaktivieren.')
    title=settings.title.strip() or project['title']
    def title_page():
        draw_block(c,title,24,40,height*.73,width-80,height*.30,True)
        draw_block(c,settings.subtitle,14,40,height*.39,width-80,height*.14,True)
        draw_block(c,settings.author,13,40,height*.18,width-80,height*.12,True)
    cover=raw.get('cover_image')
    if cover:
        with Image.open(store.asset(cover)) as source:
            im=ImageOps.exif_transpose(source).convert('RGB')
            if not draft:
                scale=min(width/im.width,height/im.height)
                if 72/scale < 299:
                    raise ValueError('Coverbild hat weniger als 300 dpi. Größeres Bild hochladen oder Layout-Entwurf wählen.')
            if project['monochrome']: im=ImageOps.grayscale(im)
            scale=min(width/im.width,height/im.height)
            w,h=im.width*scale,im.height*scale
            c.drawImage(ImageReader(im),(width-w)/2,(height-h)/2,w,h)
    else: title_page()
    c.showPage()  # Page 1: cover or generated title.
    c.showPage()  # Page 2: blank; preserves spread parity.
    title_page()
    c.showPage()  # Page 3: inside title.
    draw_block(c,settings.imprint,9,42,height-65,width-84,height-115)
    c.showPage()  # Page 4: imprint; deliberately no running header or page number.
