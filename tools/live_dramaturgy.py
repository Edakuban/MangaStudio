"""Opt-in local review of a deliberately repetitive synthetic storyboard; never edits a user book."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store,ROOT
from mangastudio.importer import import_book,chunks
from mangastudio.models import Scene,Panel,uid
from mangastudio.engine import Worker
from mangastudio.dramaturgy import review_storyboard,story_signature

store=Store(ROOT/'tmp'/'dramaturgy-live')
project=import_book(store,'Dramaturgietest.txt',('Kapitel 1\n\n'
    'Die erwachsene Archivarin Mara betrat die verlassene Bahnstation.\n\n'
    'Auf einer Bank entdeckte sie ein offenes Notizbuch. Auf der Seite war genau dieser Bahnsteig gezeichnet. '
    'Mara beugte sich über das Buch und betrachtete die Zeichnung.\n\n'
    'Hinter ihr knarrte eine Tür. Mara fuhr erschrocken herum und sah den erwachsenen Boten Ivo, der ihr zuwinkte.').encode('utf-8'))
cast=[]
for name in ('Mara','Ivo'):
    c={'id':uid(),'name':name,'description':'Adult archivist.' if name=='Mara' else 'Adult messenger.','aliases':'','image':''}
    store.write('characters',c,project['id']);cast.append(c)
chapter=store.list('chapters',project['id'])[0]
rows=dict(row for part in chunks(chapter['text']) for row in part)
chapter['scenes']=[Scene(title='Die Entdeckung',source_start=1,source_end=3,source_excerpt=rows[1],
    panels=[Panel(description='Mara steht in der leeren Station und schaut zum Fenster.',
        visual_prompt='An adult archivist standing in an empty station looking at the window.',characters=[cast[0]['id']]) for _ in range(3)]).model_dump()]
store.write('chapters',chapter,project['id'],chapter['position'])
before=copy.deepcopy(chapter)
ident=store.enqueue(project['id'],chapter['id'],'dramaturgy',{'story_signature':story_signature(chapter)})
try:
    review_storyboard(Worker(store),store.job(ident))
    store.update_job(ident,state='done',progress=1)
except Exception as exc:
    store.update_job(ident,state='failed',message=str(exc));raise
after=store.get('chapters',chapter['id'])
assert after['scenes']==before['scenes'] and after['revision']==before['revision']
review=after['dramaturgy_review']
assert review['suggestions'],'Expected findings for the deliberate repetition.'
report={'project_id':project['id'],'chapter_id':chapter['id'],'storyboard_unchanged':True,
        'suggestions':[{'title':f['title'],'action':f['action'],'category':f['category']} for f in review['suggestions']]}
(ROOT/'tmp'/'dramaturgy-live-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
