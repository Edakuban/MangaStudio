"""Character-image draft from an immutable author-description snapshot."""
from PIL import Image
from .models import uid
from .engine import image_graph
from .vendor.comfy import ComfyClient


def generate_character_image(worker, job):
    store, payload = worker.store, job['payload']
    project = store.get('projects', job['project_id'])
    cid = payload['character_id']
    if cid not in {c['id'] for c in store.list('characters', project['id'])}:
        raise ValueError('Charakter gehört nicht zu diesem Buch.')
    char = store.get('characters', cid)
    # A crash between saving the draft and updating the job must not generate twice.
    draft = char.get('manga_draft', {})
    if draft.get('job_id') == job['id'] and store.asset(draft['image']).is_file():
        return
    settings = store.settings()
    worker.update(job, payload['name']+': Charakterbild aus Beschreibung erzeugen', .1)
    prompt = ('Create a manga character reference illustration of exactly one fictional character. '
        'Use the author description below as the character design specification. '
        'Clear recognizable face, readable hairstyle, clothing and silhouette. '
        'Relaxed neutral stance, arms visible, hands outside pockets, no action scene. '
        'Isolate the character against a completely plain pure white background.\nArt direction: '+payload['style']+
        '\nCharacter name: '+payload['name']+'\nAuthor character description: '+payload['description']+
        '\nCHARACTER REFERENCE COMPOSITION (takes priority over setting or atmosphere in the description and art direction): '
        'Draw only the single character and their worn clothing, accessories and explicitly held personal items. '
        'Keep the entire background uniformly pure white, including the space around the silhouette. '
        'No scenery, room, architecture, landscape, furniture, floor, horizon, background textures, gradients, '
        'cast shadows, decorative framing or atmospheric effects. Do not depict a location from the description. '
        'Single-character reference portrait, no extra people, no panels, text, labels, speech bubbles or watermark.')
    graph = image_graph(settings, prompt, [], 768, 1024, int(job['id'][:10], 16))
    graph['13']['inputs']['filename_prefix'] = f'MangaStudio/{project["id"]}/characters/{cid}'
    client = ComfyClient(settings.comfy_url)
    result = worker.run(job, graph, 'character-description:'+cid, client, settings)
    files = [f for f in result.output_files if f.lower().endswith(('.png', '.jpg', '.webp'))]
    if not files:
        worker.clear_remote(job)
        raise ValueError('Die Bild-KI hat kein Charakterbild zurückgegeben.')
    relative = f'books/{project["id"]}/character-drafts/{cid}-{uid()[:8]}.png'
    target = store.asset(relative)
    client.download_output(files[-1], target)
    with Image.open(target) as image:
        image.verify()
    char['manga_draft'] = {'origin': 'description', 'description': payload['description'],
        'image': relative, 'style': payload['style'], 'job_id': job['id']}
    store.write('characters', char, project['id'])
    payload['completed_image'] = relative
    payload.pop('remote', None)
    store.update_job(job['id'], payload=payload)
    worker.update(job, 'Charakterbild fertig – Entwurf im Profil prüfen und übernehmen', 1)
