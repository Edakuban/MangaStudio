"""Opt-in local AI integration test using synthetic text, never an uploaded book."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.importer import import_book
from mangastudio.engine import Worker
from mangastudio.models import uid


store = Store(ROOT / 'tmp' / 'live-smoke')
project = import_book(store, 'Techniktest.txt', ('Kapitel 1\n\n'
    'Die erwachsene Archivarin Mara betritt eine verlassene Bahnstation. '
    'Eine kaputte Uhr hängt über dem Bahnsteig. Mara bleibt stehen und öffnet ihr Notizbuch. '
    'Auf der letzten Seite findet sie die Zeichnung genau dieser Station. '
    'Sie hebt den Blick, als im Tunnel ein einzelnes Licht erscheint.').encode('utf-8'))
chapter = store.list('chapters', project['id'])[0]
store.write('characters', {'id': uid(), 'name': 'Mara', 'aliases': '',
    'description': 'Adult archivist, 28 years old, short dark hair, pale long coat, carries a notebook.', 'image': ''}, project['id'])
worker = Worker(store)
job_id = store.enqueue(project['id'], chapter['id'], 'plan')
print('PLANNING', job_id, flush=True)
job = store.job(job_id)
try:
    worker.plan(job)
    store.update_job(job_id, state='done', progress=1, message='Live-Planung bestanden')
except Exception as exc:
    store.update_job(job_id, state='failed', message=str(exc))
    raise
chapter = store.get('chapters', chapter['id'])
panels = [p for s in chapter['scenes'] for p in s['panels']]
print('PLANNED', len(chapter['scenes']), 'scenes', len(panels), 'panels', flush=True)
job_id = store.enqueue(project['id'], chapter['id'], 'images', {'panel_id': panels[0]['id'], 'missing_only': False})
try:
    worker.images(store.job(job_id))
    store.update_job(job_id, state='done', progress=1, message='Live-Bildtest bestanden')
except Exception as exc:
    store.update_job(job_id, state='failed', message=str(exc))
    raise
chapter = store.get('chapters', chapter['id'])
report = {'project': project['id'], 'chapter': chapter['id'], 'scenes': len(chapter['scenes']),
          'panels': len(panels), 'image': chapter['scenes'][0]['panels'][0]['image']}
(ROOT / 'tmp' / 'live-smoke-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report), flush=True)
