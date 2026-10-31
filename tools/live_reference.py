"""Opt-in follow-up: use the synthetic first panel as a character reference."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.engine import Worker

report = json.loads((ROOT / 'tmp' / 'live-smoke-result.json').read_text())
store = Store(ROOT / 'tmp' / 'live-smoke')
chapter = store.get('chapters', report['chapter'])
char = store.list('characters', report['project'])[0]
char['image'] = report['image']
store.write('characters', char, report['project'])
panel = chapter['scenes'][-1]['panels'][-1]
panel['characters'] = [char['id']]
store.write('chapters', chapter, report['project'], chapter['position'])
ident = store.enqueue(report['project'], chapter['id'], 'images', {'panel_id': panel['id'], 'missing_only': False})
try:
    Worker(store).images(store.job(ident))
    store.update_job(ident, state='done', progress=1, message='Referenztest bestanden')
except Exception as exc:
    store.update_job(ident, state='failed', message=str(exc))
    raise
chapter = store.get('chapters', chapter['id'])
image = chapter['scenes'][-1]['panels'][-1]['image']
report['reference_test_image'] = image
(ROOT / 'tmp' / 'live-smoke-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(image)
