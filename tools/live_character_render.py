"""Opt-in local integration test with a synthetic render, no user characters."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.models import uid, BookSettings
from mangastudio.engine import Worker, image_graph
from mangastudio.character_render import generate_character_render
from mangastudio.vendor.comfy import ComfyClient

store = Store(ROOT / 'tmp' / 'character-render-live')
settings = store.settings()
client = ComfyClient(settings.comfy_url)
source_path = store.asset('synthetic-source.png')
if not source_path.is_file():
    print('Generating synthetic 3D character render for the test', flush=True)
    graph = image_graph(settings,
        'A clean stylized 3D character render of one adult female archivist, age 30, '
        'short silver bob haircut, round glasses, dark blue long coat over a cream shirt, '
        'holding a small closed brown notebook. Upper body portrait, neutral gray studio '
        'background, soft studio lighting, detailed three-dimensional materials, no text, '
        'no panels, no borders, no speech bubbles.', [], 768, 1024, 25426)
    result = client.run_workflow(graph, timeout_sec=1800)
    if not result.ok:
        raise RuntimeError(result.error)
    client.download_output(result.output_files[-1], source_path)
project = {'id': uid(), **BookSettings(title='Charakterrender-Techniktest').model_dump(), 'exports': [], 'warnings': []}
store.write('projects', project)
char = {'id': uid(), 'name': 'Testarchivarin', 'description': 'Adult archivist with a notebook.', 'aliases': '', 'image': '', 'render_source': 'synthetic-source.png'}
store.write('characters', char, project['id'])
job_id = store.enqueue(project['id'], None, 'character_render', {'character_id': char['id'],
    'source_image': char['render_source'], 'name': char['name'], 'description': char['description'], 'style': project['style']})
print('Analyze render and generate manga character', job_id, flush=True)
try:
    generate_character_render(Worker(store), store.job(job_id))
    store.update_job(job_id, state='done', progress=1, message='Live-Charaktertest bestanden')
except Exception as exc:
    store.update_job(job_id, state='failed', message=str(exc))
    raise
char = store.get('characters', char['id'])
assert char['image'] == '', 'Active reference must remain untouched until approval'
report = {'source': str(source_path), 'image': str(store.asset(char['manga_draft']['image'])),
          'analysis': char['manga_draft']['analysis'], 'active_reference_unchanged': True}
(ROOT / 'tmp' / 'character-render-live-result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
