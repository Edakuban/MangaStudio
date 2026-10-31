"""Opt-in local text-model pose check, isolated synthetic chapter and cast."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.importer import import_book
from mangastudio.models import Scene, Panel, uid
from mangastudio.engine import Worker, pose_instructions
from mangastudio.poses import generate_poses

store = Store(ROOT/'tmp'/'poses-live')
project = import_book(store, 'Posentest.txt',
    'Kapitel 1\n\nMara kniete auf dem Boden und untersuchte mit beiden Händen einen Anhänger. '
    'Ivo stand neben ihr, zeigte mit dem rechten Zeigefinger auf die Tür und sah dorthin.'.encode('utf-8'))
cast = []
for name in ['Mara', 'Ivo']:
    char = {'id': uid(), 'name': name, 'description': 'Adult traveler. Standing with one hand in a pocket.', 'aliases': '', 'image': ''}
    store.write('characters', char, project['id'])
    cast.append(char)
chapter = store.list('chapters', project['id'])[0]
panel = Panel(description='Mara kniet und untersucht mit beiden Händen einen Anhänger. Ivo steht neben ihr, zeigt mit rechts zur Tür und blickt dorthin.',
    visual_prompt='Mara kneeling, examining a pendant with both hands; Ivo standing beside her pointing at the door with his right index finger.',
    characters=[c['id'] for c in cast])
chapter['scenes'] = [Scene(title='Der Anhänger', source_start=1, source_end=1,
    source_excerpt='Mara kniete auf dem Boden', panels=[panel]).model_dump()]
store.write('chapters', chapter, project['id'], chapter['position'])
ident = store.enqueue(project['id'], chapter['id'], 'poses', {'revision': chapter['revision']})
try:
    generate_poses(Worker(store), store.job(ident))
    store.update_job(ident, state='done', progress=1)
except Exception as exc:
    store.update_job(ident, state='failed', message=str(exc))
    raise
saved = store.get('chapters', chapter['id'])['scenes'][0]['panels'][0]
assert set(saved['character_poses']) == {c['id'] for c in cast}
print(json.dumps({c['name']: saved['character_poses'][c['id']] for c in cast}, ensure_ascii=False), flush=True)
assert 'override any pose' in pose_instructions(saved, cast)
generate_poses(Worker(store), store.job(ident))
print('PASS: Both poses saved; resuming the completed panel is a no-op.', flush=True)
