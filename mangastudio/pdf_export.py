"""B5 digital manga PDF with vector text, bounded bubbles and image cropping."""
from io import BytesIO
from pathlib import Path
import re
from PIL import Image, ImageOps
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from .layout import book_pages, PAGE_W, PAGE_H
from .lettering import FONT, panel_lettering
from .print_quality import pixels_for_points,PAGE_WIDTH_MM,PAGE_HEIGHT_MM
from .publication import draw_publication, publication_count

def draw_lettering(c, lettering, x, top):
    for bubble in lettering['bubbles']:
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(.08, .08, .08)
        c.setLineWidth(.75)
        c.setDash(2, 2) if bubble['shape'] == 'whisper' else c.setDash()
        path = c.beginPath()
        for i, (px, py) in enumerate(bubble['points']):
            (path.moveTo if i == 0 else path.lineTo)(x+px, top-py)
        path.close()
        c.drawPath(path, fill=1, stroke=1)
        for cx, cy, radius in bubble['thought_dots']:
            c.circle(x+cx, top-cy, radius, fill=1, stroke=1)
        c.setDash()
        c.saveState()
        clip = c.beginPath()
        clip.rect(x+bubble['x']+bubble['width']*.13, top-bubble['y']-bubble['height']*.86,
                  bubble['width']*.74, bubble['height']*.72)
        c.clipPath(clip, stroke=0)
        c.setFillColorRGB(.04, .04, .04)
        c.setFont(FONT, bubble['font_size'])
        for i, line in enumerate(bubble['lines']):
            c.drawCentredString(x+bubble['text_x'], top-bubble['text_y']-i*bubble['font_size']*1.24, line)
        c.restoreState()
    caption = lettering['caption']
    if caption:
        c.setFillColorRGB(1, 1, 1)
        c.setStrokeColorRGB(.08, .08, .08)
        c.rect(x+caption['x'], top-caption['y']-caption['height'], caption['width'], caption['height'], fill=1, stroke=1)
        c.setFillColorRGB(.04, .04, .04)
        c.setFont(FONT, caption['font_size'])
        for i, line in enumerate(caption['lines']):
            c.drawString(x+caption['x']+6, top-caption['y']-6-caption['font_size']-i*caption['font_size']*1.24, line)


def lines_for(text, font_size, width):
    words = text.split()
    lines, line = [], ''
    for word in words:
        # Split long words deterministically instead of letting them overflow a bubble.
        fragments = []
        while pdfmetrics.stringWidth(word, FONT, font_size) > width:
            cut = max(1, len(word)-1)
            while cut > 1 and pdfmetrics.stringWidth(word[:cut]+'-', FONT, font_size) > width:
                cut -= 1
            fragments.append(word[:cut]+'-')
            word = word[cut:]
        fragments.append(word)
        for fragment in fragments:
            candidate = (line+' '+fragment).strip()
            if line and pdfmetrics.stringWidth(candidate, FONT, font_size) > width:
                lines.append(line)
                line = fragment
            else:
                line = candidate
    if line:
        lines.append(line)
    return lines or ['']


def fitted(text, width, height, maximum=11):
    for size in (maximum, maximum-1, maximum-2, 8, 7):
        lines = lines_for(text, size, width)
        if len(lines)*size*1.24 <= height:
            return size, lines
    raise ValueError('Ein Dialog ist für dieses Panel zu lang. Text kürzen oder das Panel als Splash-Seite markieren.')


def draw_text(c, text, x, top, width, height, *, bubble=False, maximum=11):
    # Coordinates are physical points with a top-oriented origin.
    padding = 6
    size, lines = fitted(text, width-2*padding, height-2*padding, maximum=maximum)
    used = len(lines)*size*1.24 + 2*padding
    bottom = top-used
    c.setFillColorRGB(1, 1, 1)
    c.setStrokeColorRGB(.08, .08, .08)
    c.setLineWidth(.7)
    c.roundRect(x, bottom, width, used, min(14, used/3) if bubble else 1, fill=1, stroke=1)
    if bubble:
        path = c.beginPath()
        path.moveTo(x+width*.68, bottom+.4)
        path.lineTo(x+width*.61, bottom-7)
        path.lineTo(x+width*.79, bottom+.4)
        c.drawPath(path, fill=1, stroke=1)
    c.setFillColorRGB(.04, .04, .04)
    c.setFont(FONT, size)
    for i, line in enumerate(lines):
        c.drawString(x+padding, top-padding-size-i*size*1.24, line)
    return used+10


def image_crop(store, panel, width, height, mono):
    image = Image.open(store.asset(panel['image'])).convert('RGB')
    image = ImageOps.exif_transpose(image)
    result = ImageOps.fit(image, pixels_for_points(width,height),
                          Image.Resampling.LANCZOS, centering=(panel.get('focus_x', .5), panel.get('focus_y', .45)))
    if mono:
        result = ImageOps.grayscale(result)
    return ImageReader(result)


def export_pdf(store, project, chapters, target, draft=False):
    if not draft:
        from .page_flow import flow_errors,ordered_panels,structure_signature
        from .layout import pages_for_chapter
        start=1
        for chapter in chapters:
            active=chapter.get('page_flow_active')
            if active and active.get('enabled',True):
                if active['structure_signature']!=structure_signature(chapter):
                    raise ValueError('Ein aktiver Seitenplan passt nicht mehr zu den Panels. Seitenplan aktualisieren oder zurücksetzen.')
                errors=flow_errors(active['plan'],[p['id'] for p in ordered_panels(chapter)],start)
                if errors:raise ValueError('Seitenablauf prüfen: '+' '.join(errors))
            start+=len(pages_for_chapter(chapter,project['direction'],start))
    pages = book_pages(chapters, project['direction'])
    if not pages:
        raise ValueError('Es gibt noch kein Storyboard für den Export.')
    missing = [p for page in pages for p in page['panels'] if not p.get('image') or not store.asset(p['image']).is_file()]
    if missing and not draft:
        raise ValueError(f'{len(missing)} Panelbilder fehlen. Bilder erzeugen oder ausdrücklich einen Layout-Entwurf exportieren.')
    page_w, page_h = PAGE_WIDTH_MM*mm, PAGE_HEIGHT_MM*mm
    sx, sy = page_w/PAGE_W, page_h/PAGE_H
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp.pdf')
    c = canvas.Canvas(str(temporary), pagesize=(page_w, page_h), pageCompression=1)
    c.setTitle(project['title'])
    c.setAuthor('MangaStudio')
    c.setViewerPreference('Direction', 'R2L' if project['direction'] == 'rtl' else 'L2R')
    c._doc.Catalog.setPageLayout('TwoPageLeft' if project['direction'] == 'rtl' else 'TwoPageRight')
    try:
        draw_publication(c,store,project,page_w,page_h,draft)
        for page in pages:
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
            c.setFillColorRGB(.18, .18, .18)
            c.setFont(FONT, 8)
            if page.get('layout') != 'full_bleed':
                c.drawString(24, page_h-25, page['chapter_title'][:90])
                c.drawRightString(page_w-24, 17, f"{page['number']+publication_count(project):02}")
            if draft:
                c.setFont(FONT, 6)
                c.drawString(24, 17, 'LAYOUT-ENTWURF / fehlende Bilder als Platzhalter')
            for panel in page['panels']:
                box = panel['box']
                x, top, w, h = box['x']*sx, page_h-box['y']*sy, box['w']*sx, box['h']*sy
                y = top-h
                c.saveState()
                clip = c.beginPath()
                polygon = panel.get('polygon')
                if polygon:
                    for i, (px, py) in enumerate(polygon):
                        (clip.moveTo if i == 0 else clip.lineTo)(px*sx, page_h-py*sy)
                    clip.close()
                else:
                    clip.rect(x, y, w, h)
                c.clipPath(clip, stroke=0)
                if panel.get('image') and store.asset(panel['image']).is_file():
                    c.drawImage(image_crop(store, panel, w, h, project['monochrome']), x, y, w, h)
                else:
                    c.setFillColorRGB(.93, .93, .92)
                    c.rect(x, y, w, h, fill=1, stroke=0)
                    c.setStrokeColorRGB(.78, .78, .77)
                    for k in range(-600, 1600, 25):
                        c.line(x+k, y, x+k+h, top)
                    c.setFillColorRGB(.2, .2, .2)
                    c.setFont(FONT, 9)
                    c.drawCentredString(x+w/2, y+h/2+8, f"PANEL {panel['order']:02} / BILD FEHLT")
                    desc = lines_for(panel['description'], 8, w-24)[:4]
                    c.setFont(FONT, 8)
                    for i, line in enumerate(desc):
                        c.drawCentredString(x+w/2, y+h/2-8-i*11, line)
                lettering = panel['lettering']
                if lettering['issues'] and not draft:
                    raise ValueError(f'Panel {panel["order"]}: '+ ' '.join(lettering['issues']))
                draw_lettering(c, lettering, x, top)
                c.restoreState()
                c.setStrokeColorRGB(.05, .05, .05)
                c.setLineWidth(1.1)
                if panel.get('border', 'framed') != 'open' and page.get('layout') != 'full_bleed':
                    if polygon:
                        frame = c.beginPath()
                        for i, (px, py) in enumerate(polygon):
                            (frame.moveTo if i == 0 else frame.lineTo)(px*sx, page_h-py*sy)
                        frame.close()
                        c.drawPath(frame, fill=0, stroke=1)
                    else:
                        c.rect(x, y, w, h, fill=0, stroke=1)
            c.showPage()
        c.save()
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return len(pages)+publication_count(project)
