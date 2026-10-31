"""Opt-in local AI test: stage a chapter page sequence, never alter a user book."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store,ROOT
from mangastudio.demo import create_demo
from mangastudio.engine import Worker
from mangastudio.dramaturgy import story_signature
from mangastudio.page_flow import context_for,plan_page_flow,flow_errors,ordered_panels

store=Store(ROOT/'tmp'/'page-flow-live')
project=create_demo(store)
chapter=store.list('chapters',project['id'])[0]
before=copy.deepcopy(chapter)
context=context_for(store,chapter,project)
ident=store.enqueue(project['id'],chapter['id'],'page_flow',{
    'story_signature':story_signature(chapter),'context_signature':context['signature']})
try:
    plan_page_flow(Worker(store),store.job(ident));store.update_job(ident,state='done',progress=1)
except Exception as exc:
    store.update_job(ident,state='failed',message=str(exc));raise
after=store.get('chapters',chapter['id'])
assert after['scenes']==before['scenes'] and after['revision']==before['revision']
assert not flow_errors(after['page_flow_proposal']['plan'],[p['id'] for p in ordered_panels(chapter)],context['start_page'])
report={'project_id':project['id'],'chapter_id':chapter['id'],'storyboard_unchanged':True,
    'pages':[{'panels':len(p['panels']),'layout':p['layout'],'turn':p['turn'],'reason':p['reason']} for p in after['page_flow_proposal']['plan']['pages']]}
(ROOT/'tmp'/'page-flow-live-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
