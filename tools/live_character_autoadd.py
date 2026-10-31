"""Opt-in local AI check on synthetic text, isolated from user books."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.models import uid, BookSettings
from mangastudio.engine import Worker
from mangastudio.character_discovery import autoadd_characters

store = Store(ROOT / 'tmp' / 'character-autoadd-live')
project = {'id': uid(), **BookSettings(title='Autoadd-Techniktest').model_dump()}
store.write('projects', project)
chapter = {'id': uid(), 'project_id': project['id'], 'position': 0, 'title': 'Testkapitel',
           'text': 'Liora betrat die Werkstatt. Die Schmiedin trug einen blauen Mantel.\n\n'
                   'Kian hob den Kopf. Der Bote hatte kurzes schwarzes Haar und eine Narbe an der linken Wange. '
                   'Kian übergab Liora einen Brief. Beide verließen die Werkstatt.', 'scenes': [], 'revision': 0}
store.write('chapters', chapter, project['id'], 0)
original = {'id': uid(), 'name': 'Liora', 'description': 'Eigene unveränderte Beschreibung.', 'aliases': '', 'image': ''}
store.write('characters', original, project['id'])
for attempt in range(2):
    ident = store.enqueue(project['id'], chapter['id'], 'character_autoadd', {})
    try:
        autoadd_characters(Worker(store), store.job(ident))
        store.update_job(ident, state='done', progress=1)
    except Exception as exc:
        store.update_job(ident, state='failed', message=str(exc))
        raise
    print(json.dumps(store.job(ident)['payload']['result'], ensure_ascii=False), flush=True)
    cast = store.list('characters', project['id'])
    assert len(cast) == 2, cast
    assert {c['name'] for c in cast} == {'Liora', 'Kian'}, cast
    assert store.get('characters', original['id']) == original
print('PASS: Kian discovered once; Liora unchanged; repeat creates no duplicates.', flush=True)
