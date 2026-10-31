"""Opt-in native B5 300-dpi generation and PDF placement smoke test; synthetic data only."""
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from pypdf import PdfReader
from mangastudio.store import Store,ROOT
from mangastudio.models import Settings
from mangastudio.demo import create_demo
from mangastudio.engine import Worker
from mangastudio.pdf_export import export_pdf

started=time.monotonic()
store=Store(ROOT/'tmp'/'native-print-live')
with sqlite3.connect((ROOT/'data'/'manga.sqlite3').as_uri()+'?mode=ro',uri=True) as source:
    settings=Settings.model_validate_json(source.execute('select data from settings where id=1').fetchone()[0])
store.save_settings(settings)
book=create_demo(store)
book['style']='Detailed original manga ink illustration, expressive linework, graphic shadows.'
store.write('projects',book)
chapter=store.list('chapters',book['id'])[0];chapter['scenes']=chapter['scenes'][:1]
scene=chapter['scenes'][0];scene['layout']='full_bleed';scene['panels']=scene['panels'][:1]
panel=scene['panels'][0]
panel.update(description='Isolierter Druckauflösungstest.',visual_prompt='One old stone archway in a quiet courtyard, climbing ivy, precise masonry details, dramatic sunlight, no people, no text.',characters=[],character_poses={},bubbles=[],caption='',image='',image_signature='')
store.write('chapters',chapter,book['id'],chapter['position'])
jobid=store.enqueue(book['id'],chapter['id'],'images',{'panel_id':panel['id'],'missing_only':False})
print('Generating a native 2080 x 2960 pixel B5 test image...',flush=True)
try:
    Worker(store).images(store.job(jobid));store.update_job(jobid,state='done',progress=1)
except Exception as exc:
    store.update_job(jobid,state='failed',message=str(exc));raise
chapter=store.get('chapters',chapter['id']);panel=chapter['scenes'][0]['panels'][0]
with Image.open(store.asset(panel['image'])) as image:size=image.size
assert size==(2080,2960),size
pdf=ROOT/'tmp'/'native-300dpi-proof.pdf';export_pdf(store,book,[chapter],pdf)
page=PdfReader(pdf).pages[0];objects=page['/Resources']['/XObject'].get_object();ppi=[]
def visit(op,args,ctm,tm):
    if op!=b'Do':return
    image=objects[args[0]].get_object()
    if image.get('/Subtype')=='/Image':
        ppi.append([image['/Width']*72/math.hypot(ctm[0],ctm[1]),image['/Height']*72/math.hypot(ctm[2],ctm[3])])
page.extract_text(visitor_operand_before=visit)
assert ppi and all(min(pair)>=300 for pair in ppi),ppi
report={'image':str(store.asset(panel['image'])),'pixels':size,'pdf':str(pdf),'ppi':ppi,'seconds':round(time.monotonic()-started,1)}
(ROOT/'tmp'/'native-print-live-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
