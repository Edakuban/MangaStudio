"""Local AI layout analysis of an isolated synthetic scene, without image generation."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.demo import create_demo
from mangastudio.engine import Worker
from mangastudio.layout_advice import suggest_layout

store = Store(ROOT/'tmp'/'koma-wari-live')
project = create_demo(store)
chapter = store.list('chapters', project['id'])[0]
chapter['scenes'] = chapter['scenes'][1:2]
store.write('chapters', chapter, project['id'], chapter['position'])
before = copy.deepcopy(chapter)
ident = store.enqueue(project['id'], chapter['id'], 'layout', {'revision': chapter['revision']})
try:
    suggest_layout(Worker(store), store.job(ident))
    store.update_job(ident, state='done', progress=1)
except Exception as exc:
    store.update_job(ident, state='failed', message=str(exc))
    raise
after = store.get('chapters', chapter['id'])
for old, new in zip(before['scenes'][0]['panels'],after['scenes'][0]['panels']):
    for key in ('id','description','visual_prompt','image','bubbles','caption'):
        assert old[key] == new[key]
scene = after['scenes'][0]
print(json.dumps({key:scene[key] for key in ('layout','rhythm','layout_reason')},ensure_ascii=False),flush=True)
