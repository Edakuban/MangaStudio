"""Isolated fixture and PDF for visual review of lettering and Koma-Wari."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.demo import create_demo
from mangastudio.pdf_export import export_pdf

store = Store(ROOT/'tmp'/'lettering-layout-demo')
project = create_demo(store)
chapters = store.list('chapters', project['id'])
scene = chapters[0]['scenes'][0]
scene['layout'] = 'dynamic'
scene['rhythm'] = 'action'
scene['layout_reason'] = 'Diagonale Teilung folgt dem überraschenden Licht aus dem Tunnel.'
scene['panels'][0]['emphasis'] = 'normal'
# Four separate styles, each with clear placement and speaker metadata hidden from print.
all_panels = [p for ch in chapters for s in ch['scenes'] for p in s['panels']]
for index, p in enumerate(all_panels):
    p['bubbles'] = [{'speaker': 'Mara', 'text': ['Woher kommt dieses Licht?', 'Ob er mich hören kann?', 'Ganz leise. Nicht bewegen.', 'Zurück!'][index % 4],
                     'shape': ['speech','thought','whisper','shout'][index % 4], 'side': 'right', 'vertical': 'top',
                     'font_size': 10}]
    p['caption'] = ''
    p['image'] = ''
chapters[0]['scenes'][1]['layout'] = 'dynamic'
chapters[0]['scenes'][1]['layout_reason'] = 'Die Bewegung erhält diagonale Bildgrenzen.'
chapters[0]['scenes'][2]['layout'] = 'cinematic'
chapters[0]['scenes'][2]['layout_reason'] = 'Breite Bilder lassen dem Tunnel und der Erwartung Raum.'
chapters[1]['scenes'][-1]['layout'] = 'full_bleed'
chapters[1]['scenes'][-1]['panels'] = chapters[1]['scenes'][-1]['panels'][:1]
for ch in chapters:
    store.write('chapters', ch, project['id'], ch['position'])
target = ROOT/'tmp'/'lettering-layout-demo.pdf'
export_pdf(store, project, chapters, target, draft=True)
print(json.dumps({'project_id': project['id'], 'chapter_id': chapters[0]['id'], 'pdf': str(target)}))
