"""Shared, physical-point lettering geometry for browser SVG and PDF output."""
import math
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT = 'Helvetica'
for font_path in (Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')):
    if font_path.is_file():
        if 'MangaText' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('MangaText', str(font_path)))
        FONT = 'MangaText'
        break


def wrap_text(text, size, width):
    """Keep intentional line breaks and split long words without going outside the box."""
    lines = []
    width = max(8, width)
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            while pdfmetrics.stringWidth(word, FONT, size) > width:
                cut = max(1, len(word)-1)
                while cut > 1 and pdfmetrics.stringWidth(word[:cut]+'-', FONT, size) > width:
                    cut -= 1
                if line:
                    lines.append(line)
                    line = ''
                lines.append(word[:cut]+'-')
                word = word[cut:]
            candidate = (line+' '+word).strip()
            if line and pdfmetrics.stringWidth(candidate, FONT, size) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines or ['']


def outline(x, y, w, h, shape, tail):
    count = 80 if shape == 'thought' else (32 if shape == 'shout' else 64)
    points = []
    for i in range(count):
        angle = 2*math.pi*i/count
        radius = (1 if i % 2 == 0 else .83) if shape == 'shout' else (1+.06*math.sin(angle*10) if shape == 'thought' else 1)
        # Cloud lobes are contained in the user-selected frame.
        radius /= 1.06 if shape == 'thought' else 1
        points.append([x+w/2+math.cos(angle)*w/2*radius, y+h/2+math.sin(angle)*h/2*radius])
    if tail and shape != 'thought':
        tx, ty = tail
        if ((tx-x-w/2)/(w/2))**2+((ty-y-h/2)/(h/2))**2 > 1.1:
            closest = min(range(count), key=lambda i: (points[i][0]-tx)**2+(points[i][1]-ty)**2)
            # Replace a small arc with a pointed tail, leaving a single continuous contour.
            points = [points[(closest+2+j) % count] for j in range(count-3)] + [[tx, ty]]
    return [[round(px, 3), round(py, 3)] for px, py in points]


def intersects(a, b):
    return min(a['x']+a['width'], b['x']+b['width']) > max(a['x'], b['x'])+1 and min(a['y']+a['height'], b['y']+b['height']) > max(a['y'], b['y'])+1


def panel_lettering(panel, width, height, safe_left=0, safe_right=None):
    """Coordinates are panel-local points, with origin at the upper left."""
    issues, bubbles = [], []
    safe_right = width if safe_right is None else safe_right
    safe_width = safe_right-safe_left
    caption = None
    if panel.get('caption'):
        lines = wrap_text(panel['caption'], 9, safe_width-24)
        cap_h = len(lines)*11.16+12
        caption = {'x': safe_left+6, 'y': height-6-cap_h, 'width': safe_width-12, 'height': cap_h,
                   'font_size': 9, 'lines': lines}
        if cap_h > height*.3:
            issues.append('Erzählkasten ist für dieses Panel zu lang.')
    upper, lower = 7, caption['y']-12 if caption else height-14
    source = panel.get('bubbles', [])
    # Bottom group is packed backwards, while logical dialogue order stays unchanged.
    order = [i for i, b in enumerate(source) if b.get('vertical', 'top') == 'top'] + list(reversed([i for i, b in enumerate(source) if b.get('vertical') == 'bottom']))
    for i in order:
        b = source[i]
        size = b.get('font_size', 10)
        shape = b.get('shape', 'speech')
        inner_w, inner_h = (.60, .56) if shape == 'shout' else ((.66, .62) if shape == 'thought' else (.72, .68))
        longest = max(pdfmetrics.stringWidth(line, FONT, size) for line in b['text'].split('\n'))
        bw = b['width']*width if b.get('width') is not None else min(.85*safe_width, max(60, .35*safe_width, longest/inner_w+12))
        bw = min(width-8, bw)
        lines = wrap_text(b['text'], size, bw*inner_w)
        needed = (len(lines)*size*1.24+6)/inner_h
        auto_h = min(needed, max(22, height*(.60 if caption else .70)/max(1, len(source))))
        bh = (b['height']*height) if b.get('height') is not None else auto_h
        bh = min(height-4, bh)
        bx = b['x']*width if b.get('x') is not None else (safe_right-bw-6 if b.get('side', 'right') == 'right' else safe_left+6)
        by = b['y']*height if b.get('y') is not None else (lower-bh if b.get('vertical') == 'bottom' else upper)
        bx, by = max(2, min(bx, width-bw-2)), max(2, min(by, height-bh-2))
        if b.get('vertical') == 'bottom':
            lower = by-12
        else:
            upper = by+bh+12
        tail = None
        if b.get('show_tail', True):
            tail = [b['tail_x']*width if b.get('tail_x') is not None else bx+bw*.65,
                    b['tail_y']*height if b.get('tail_y') is not None else min(height-3, by+bh+10)]
        frame = {'index': i, 'x': bx, 'y': by, 'width': bw, 'height': bh, 'font_size': size,
                 'shape': b.get('shape', 'speech'), 'lines': lines, 'tail': tail,
                 'text_x': bx+bw/2, 'text_y': by+bh/2-(len(lines)-1)*size*1.24/2+size*.33}
        frame['points'] = outline(bx, by, bw, bh, frame['shape'], tail)
        frame['thought_dots'] = []
        if tail and frame['shape'] == 'thought':
            cx, cy = bx+bw/2, by+bh/2
            dx, dy = tail[0]-cx, tail[1]-cy
            length = math.sqrt((dx/(bw/2))**2+(dy/(bh/2))**2)
            if length > 1:
                ex, ey = cx+dx/length, cy+dy/length
                for amount, radius in ((.3, 2.5), (.65, 1.8), (1, 1.1)):
                    frame['thought_dots'].append([ex+(tail[0]-ex)*amount, ey+(tail[1]-ey)*amount, radius])
        if needed > bh+.1:
            issues.append(f'Sprechblase {i+1}: Text passt bei {size:g} pt nicht. Blase vergrößern oder Text kürzen.')
        if caption and intersects(frame, caption):
            issues.append(f'Sprechblase {i+1} überdeckt den Erzählkasten.')
        for other in bubbles:
            if intersects(frame, other):
                issues.append(f'Sprechblasen {other["index"]+1} und {i+1} überlappen.')
        bubbles.append(frame)
    return {'width': width, 'height': height, 'bubbles': sorted(bubbles, key=lambda b: b['index']), 'caption': caption, 'issues': issues}


def page_lettering(page):
    sx, sy = 176*72/25.4/1000, 250*72/25.4/1420
    for panel in page['panels']:
        box = panel['box']
        safe_left, safe_right = 0, box['w']*sx
        if panel.get('polygon'):
            rows = {}
            for x, y in panel['polygon']:
                rows.setdefault(round(y, 4), []).append(x)
            if all(len(xs) >= 2 for xs in rows.values()):
                safe_left = (max(min(xs) for xs in rows.values())-box['x'])*sx
                safe_right = (min(max(xs) for xs in rows.values())-box['x'])*sx
        panel['lettering'] = panel_lettering(panel, box['w']*sx, box['h']*sy, safe_left, safe_right)
        if panel.get('polygon'):
            polygon = [[(x-box['x'])*sx, (y-box['y'])*sy] for x, y in panel['polygon']]
            def inside(point):
                crosses = [(b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
                return all(v >= -.1 for v in crosses) or all(v <= .1 for v in crosses)
            for bubble in panel['lettering']['bubbles']:
                if not all(inside(point) for point in bubble['points']):
                    panel['lettering']['issues'].append(f'Sprechblase {bubble["index"]+1} wird am schrägen Panelrand abgeschnitten. Position oder Größe anpassen.')
    return page
