"""Opt-in local image-generation test on a synthetic character, no user data."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.models import uid, BookSettings
from mangastudio.engine import Worker
from mangastudio.character_generation import generate_character_image

store = Store(ROOT/'tmp'/'character-description-live')
project = {'id': uid(), **BookSettings(title='Beschreibung-Bild-Techniktest').model_dump()}
store.write('projects', project)
char = {'id': uid(), 'name': 'Testarchivarin', 'aliases': '', 'image': '',
        'description': 'An adult female archivist, age 30, short silver bob haircut, round glasses, '
                       'dark long coat over a cream shirt, a small closed brown notebook in one hand.'}
store.write('characters', char, project['id'])
ident = store.enqueue(project['id'], None, 'character_generate', {
    'character_id': char['id'], 'name': char['name'], 'description': char['description'], 'style': project['style']})
try:
    generate_character_image(Worker(store), store.job(ident))
    store.update_job(ident, state='done', progress=1)
except Exception as exc:
    store.update_job(ident, state='failed', message=str(exc))
    raise
saved = store.get('characters', char['id'])
assert saved['image'] == '' and saved['description'] == char['description']
assert saved['manga_draft']['origin'] == 'description'
report = {'image': str(store.asset(saved['manga_draft']['image'])), 'active_reference_unchanged': True}
(ROOT/'tmp'/'character-description-live-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report), flush=True)
