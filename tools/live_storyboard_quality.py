"""Opt-in local storyboard test on synthetic prose; no user chapters or image generation."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.importer import import_book
from mangastudio.engine import Worker
from mangastudio.models import uid
from mangastudio.storyboard_quality import repeated_panels

store = Store(ROOT/'tmp'/'storyboard-quality-live')
project = import_book(store, 'Bewegung.txt', ('Kapitel 1\n\n'
    'Die erwachsene Archivarin Mara öffnete die Tür der verlassenen Station und trat ein.\n\n'
    'Am Fahrkartenschalter fand sie ein altes Notizbuch. Sie schlug es auf und betrachtete die Zeichnung einer Uhr.\n\n'
    'Ein Geräusch ließ sie aufblicken. Auf dem Bahnsteig stand der erwachsene Bote Ivo und winkte ihr zu.\n\n'
    'Mara schloss das Notizbuch und ging zu Ivo auf den Bahnsteig.').encode('utf-8'))
chapter = store.list('chapters', project['id'])[0]
for name in ('Mara', 'Ivo'):
    store.write('characters', {'id': uid(), 'name': name, 'aliases': '',
        'description': 'Adult archivist with a notebook.' if name == 'Mara' else 'Adult messenger.', 'image': ''}, project['id'])
ident = store.enqueue(project['id'], chapter['id'], 'plan', {})
try:
    Worker(store).plan(store.job(ident))
    store.update_job(ident, state='done', progress=1)
except Exception as exc:
    store.update_job(ident, state='failed', message=str(exc))
    raise
saved = store.get('chapters', chapter['id'])
assert not repeated_panels(saved['scenes'])
print(json.dumps({'scenes': len(saved['scenes']), 'panels': sum(len(s['panels']) for s in saved['scenes']),
                  'duplicate_panels': 0, 'descriptions': [p['description'] for s in saved['scenes'] for p in s['panels']]}, ensure_ascii=False), flush=True)
