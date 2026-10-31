"""Narrative-weighted page packing; coordinates use a 1000 x 1420 canvas."""
from .models import Scene

PAGE_W, PAGE_H = 1000, 1420
BOX = (48, 100, 904, 1240)


def layout_polygons(count, style, direction):
    """Non-overlapping polygon templates in reading order, normalized to the page area."""
    if style == 'dynamic' and count > 1:
        if count == 2:
            bands = [(0, 1, 2)]
        elif count == 3:
            bands = [(0, .34, 1), (.36, 1, 2)]
        elif count == 4:
            bands = [(0, .49, 2), (.51, 1, 2)]
        else:
            bands = [(0, .28, 1), (.30, .64, 2), (.66, 1, 2)]
        polygons = []
        for top, bottom, slots in bands:
            if slots == 1:
                polygons.append([(0, top), (1, top), (1, bottom), (0, bottom)])
            else:
                polygons.extend([[(0, top), (.57, top), (.43, bottom), (0, bottom)],
                                 [(.59, top), (1, top), (1, bottom), (.45, bottom)]])
    elif style == 'cinematic':
        gap = .018
        heights = [1/count-gap*(count-1)/count]*count
        if count > 1:
            heights[0] += .12
            for i in range(1, count):
                heights[i] -= .12/(count-1)
        polygons, at = [], 0
        for height in heights:
            polygons.append([(0, at), (1, at), (1, at+height), (0, at+height)])
            at += height+gap
    else:
        return None
    if direction == 'rtl':
        polygons = [[(1-x, y) for x, y in poly] for poly in polygons]
    return polygons


def page_geometry(count, style, variant, emphasis, direction):
    if style == 'full_bleed':
        return [({'x': 0, 'y': 0, 'w': PAGE_W, 'h': PAGE_H}, None)]
    polygons = layout_polygons(count, style, direction)
    if polygons is None:
        return [(box, None) for box in layout_boxes(count, variant, emphasis, direction)]
    x0, y0, w0, h0 = BOX
    result = []
    for poly in polygons:
        points = [[x0+x*w0, y0+y*h0] for x, y in poly]
        xs, ys = zip(*points)
        result.append(({'x': min(xs), 'y': min(ys), 'w': max(xs)-min(xs), 'h': max(ys)-min(ys)}, points))
    return result


def layout_boxes(count, variant=0, first_emphasis='normal', direction='rtl'):
    g = .016
    if count == 1:
        boxes = [(0, 0, 1, 1)]
    elif count == 2:
        if first_emphasis == 'tall':
            boxes = [(0, 0, .56-g/2, 1), (.56+g/2, 0, .44-g/2, 1)]
        else:
            ratio = .62 if variant % 2 else .44
            boxes = [(0, 0, 1, ratio-g/2), (0, ratio+g/2, 1, 1-ratio-g/2)]
    elif count == 3 and (first_emphasis == 'tall' or variant % 2):
        boxes = [(0, 0, .58-g/2, 1), (.58+g/2, 0, .42-g/2, .44-g/2), (.58+g/2, .44+g/2, .42-g/2, .56-g/2)]
    elif count == 3:
        boxes = [(0, 0, 1, .45-g/2), (0, .45+g/2, .56-g/2, .55-g/2), (.56+g/2, .45+g/2, .44-g/2, .55-g/2)]
    elif count == 4 and variant % 2:
        boxes = [(0, 0, 1, .32-g/2), (0, .32+g/2, .6-g/2, .38-g), (.6+g/2, .32+g/2, .4-g/2, .38-g), (0, .7+g/2, 1, .3-g/2)]
    elif count == 4:
        boxes = [(0, 0, .6-g/2, .65-g/2), (.6+g/2, 0, .4-g/2, .32-g/2), (.6+g/2, .32+g/2, .4-g/2, .33-g), (0, .65+g/2, 1, .35-g/2)]
    elif count == 5:
        boxes = [(0, 0, 1, .34-g/2), (0, .34+g/2, .6-g/2, .34-g), (.6+g/2, .34+g/2, .4-g/2, .34-g), (0, .68+g/2, .4-g/2, .32-g/2), (.4+g/2, .68+g/2, .6-g/2, .32-g/2)]
    else:
        raise ValueError('Eine Seite unterstützt 1 bis 5 Panels.')
    if direction == 'rtl':
        boxes = [(1-x-w, y, w, h) for x, y, w, h in boxes]
    x0, y0, w0, h0 = BOX
    return [{'x': x0+x*w0, 'y': y0+y*h0, 'w': w*w0, 'h': h*h0} for x, y, w, h in boxes]


def pages_for_chapter(chapter, direction='rtl', start=1):
    from .page_flow import structure_signature,render_flow
    active=chapter.get('page_flow_active')
    if active and active.get('enabled',True) and active['structure_signature']==structure_signature(chapter):
        return render_flow(chapter,active['plan'],direction,start)
    items = []
    for scene in chapter['scenes']:
        Scene.model_validate(scene)
        for panel in scene['panels']:
            items.append({**panel, 'scene_id': scene['id'], 'scene_title': scene['title'],
                          'layout': scene.get('layout', 'auto'), 'rhythm': scene.get('rhythm', 'calm'),
                          'layout_reason': scene.get('layout_reason', '')})
    pages, at = [], 0
    while at < len(items):
        first = items[at]
        style = first['layout']
        if first['emphasis'] == 'splash' or style == 'full_bleed':
            count = 1
        else:
            count = 1
            target = 3 if first['emphasis'] in ('wide', 'tall') else (4 if len(pages) % 2 == 0 else 5)
            if style == 'cinematic':
                target = min(target, 3)
            while count < target and at+count < len(items) and items[at+count]['emphasis'] != 'splash':
                if items[at+count].get('page_break_before') or items[at+count-1].get('page_break_after'):
                    break
                if items[at+count]['layout'] != style:
                    break
                if count >= 3 and items[at+count]['emphasis'] in ('wide', 'tall'):
                    break
                count += 1
        selected = items[at:at+count]
        geometry = page_geometry(count, style, len(pages), first['emphasis'], direction)
        from .lettering import page_lettering
        pages.append(page_lettering({'number': start+len(pages), 'chapter_id': chapter['id'], 'chapter_title': chapter['title'],
                      'layout': style, 'rhythm': first['rhythm'], 'layout_reason': first['layout_reason'],
                      'panels': [{**panel, 'box': box, 'polygon': poly, 'order': at+i+1}
                                 for i, (panel, (box, poly)) in enumerate(zip(selected, geometry))]}))
        at += count
    return pages


def book_pages(chapters, direction='rtl'):
    pages = []
    for chapter in chapters:
        pages += pages_for_chapter(chapter, direction, len(pages)+1)
    return pages
