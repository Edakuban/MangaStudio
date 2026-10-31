"""Recover already-generated, source-validated text from a failed local planning job."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store
from mangastudio.importer import chunks
from mangastudio.engine import decode_plan, validate_chunk
from mangastudio.vendor.comfy import ComfyClient, extract_text_outputs

parser = argparse.ArgumentParser()
parser.add_argument('job_id')
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
store = Store()
job = store.job(args.job_id)
if job['state'] != 'failed' or job['kind'] != 'plan':
    raise SystemExit('Only failed storyboard jobs can be recovered.')
chapter = store.get('chapters', job['chapter_id'])
project = store.get('projects', job['project_id'])
cast = store.list('characters', project['id'])
client = ComfyClient(store.settings().comfy_url)
history = client.transport.get_json(client.base_url+'/history?max_items=40')
payload = job['payload']
completed = payload.setdefault('completed_chunks', [])
parts = chunks(chapter['text'])
recovered = 0
for index in range(len(completed), len(parts)):
    source = parts[index]
    expected = '\n\n'.join(f'[{number}] {text}' for number, text in source)
    matched = None
    for entry in reversed(list(history.values())):
        if not entry.get('status', {}).get('completed'):
            continue
        graph = entry.get('prompt', [None, None, {}])[2]
        prompts = [n.get('inputs', {}).get('prompt', '') for n in graph.values()
                   if isinstance(n, dict) and n.get('class_type') == 'TextGenerate']
        if not any(f'BUCH: {project["title"]}\nKAPITEL: {chapter["title"]}\n' in p and expected in p for p in prompts):
            continue
        raw = extract_text_outputs(entry)
        if raw:
            try:
                matched = validate_chunk(decode_plan(raw[-1], cast, source), source, {c['id'] for c in cast})
                break
            except ValueError as exc:
                print('Matched output could not be safely recovered:', type(exc).__name__)
    if matched is None:
        break
    completed.append(matched.model_dump())
    recovered += 1
if args.apply and recovered:
    store.update_job(job['id'], payload=payload, message=f'{recovered} bereits erzeugte Textabschnitte wiederhergestellt. Fortsetzung bereit.')
print(json.dumps({'recovered_chunks': recovered, 'completed_chunks': len(completed), 'total_chunks': len(parts), 'applied': args.apply}))
