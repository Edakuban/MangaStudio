"""Opt-in local book-style smoke test, with synthetic text and an isolated database."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store,ROOT
from mangastudio.importer import import_book
from mangastudio.book_style import analyze_book_style,book_source_signature
from mangastudio.engine import Worker

store=Store(ROOT/'tmp'/'book-style-live')
store.save_settings(Store().settings())
book=import_book(store,'harbor.txt',(
    'Chapter 1\n\nCopper pipes line the narrow alleys of a foggy harbor. Amber gas lamps reflect in wet '
    'cobblestones. The archivist wears a weathered wool coat and carries a notebook. Wooden cranes creak '
    'above iron barges. The distant lighthouse cuts a pale beam through blue mist.\n\n'
    'Chapter 2\n\nAt dawn the harbor becomes quiet. Warm light enters an archive through tall leaded '
    'windows. Wooden shelves, brass instruments and paper charts fill the hall. Outside, the same '
    'copper pipes cross the old brick walls. There are no computers or electric lights in these scenes.'
).encode())
before=store.list('chapters',book['id'])
ident=store.enqueue(book['id'],None,'book_style',{
    'source_signature':book_source_signature(store,book),'base_style':book['style']})
try:
    analyze_book_style(Worker(store),store.job(ident));store.update_job(ident,state='done',progress=1)
except Exception as exc:
    store.update_job(ident,state='failed',message=str(exc));raise
saved=store.get('projects',book['id']);assert saved['style']==book['style']
assert store.list('chapters',book['id'])==before
report={'project_id':book['id'],'job_id':ident,'active_style_unchanged':True,'draft':saved['style_draft']}
(ROOT/'tmp'/'book-style-live-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
