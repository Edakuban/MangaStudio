from contextlib import asynccontextmanager
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from .store import Store, ROOT
from .models import (Settings, CharacterInput, BookSettings, EditPlan, GenerateRequest,
                     ExportRequest, PlanRequest, PlanChunk, AcceptCharacterRender, uid)
from .importer import import_book, chunks
from .engine import Worker, validate_chunk, image_signature, ENGINE_VERSION
from .layout import book_pages, pages_for_chapter
from .pdf_export import export_pdf
from .vendor.comfy import ComfyClient
from .dramaturgy import ReviewDecision, ReviewConflict, story_signature, review_state, decide_suggestion
from .page_flow import FlowPlan,FlowDecision,context_for,flow_state,preview_flow,decide_flow,spreads,edit_active_flow
from .book_style import book_source_signature,style_parts
from .print_quality import image_is_print_ready


def create_app(data_root=None, start_worker=True):
    store = Store(data_root) if data_root else Store()
    worker = Worker(store)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.close()

    app = FastAPI(title='KOMA - MangaStudio', lifespan=lifespan)
    app.state.store = store
    app.mount('/static', StaticFiles(directory=ROOT / 'mangastudio' / 'static'), name='static')

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.headers.get('host', '').split(':')[0].lower()
        if host not in {'127.0.0.1', 'localhost', 'testserver'}:
            return JSONResponse({'detail': 'Nur lokale Verbindungen erlaubt.'}, status_code=403)
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin:
            if urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
                return JSONResponse({'detail': 'Fremde Browser-Origin abgelehnt.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': str(exc).strip("'")}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    def idle(project_id):
        store.get('projects',project_id)
        if store.busy(project_id):
            raise HTTPException(409, 'Für dieses Buch läuft ein Auftrag. Änderungen danach speichern.')

    def chapter_of(ident):
        return store.get('chapters', ident)

    def save_chapter(chapter):
        store.write('chapters', chapter, chapter['project_id'], chapter['position'])

    def owned_character(project_id, character_id):
        if character_id not in {c['id'] for c in store.list('characters', project_id)}:
            raise HTTPException(404, 'Charakter nicht gefunden.')
        return store.get('characters', character_id)

    def enqueue_character_render(project_id, character, source):
        project = store.get('projects', project_id)
        return store.enqueue(project_id, None, 'character_render', {
            'character_id': character['id'], 'source_image': source,
            'name': character['name'], 'description': character['description'], 'style': project['style'],
        })

    async def read_upload(file, limit):
        data = await file.read(limit+1)
        await file.close()
        if len(data) > limit:
            raise HTTPException(413, 'Datei ist zu groß.')
        return data

    def save_image(data, project_id, folder):
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width*image.height > 40_000_000 or min(image.size) < 64:
                    raise ValueError('Bildgröße muss zwischen 64 Pixeln und 40 Megapixeln liegen.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((4096,4096) if folder=='panels' else (2560,2560))
                relative = f'books/{project_id}/{folder}/{uid()}.png'
                path = store.asset(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path)
                return relative
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValueError('Bitte eine gültige PNG-, JPEG- oder WebP-Datei hochladen.') from None

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'mangastudio' / 'static' / 'index.html')

    @app.get('/health')
    def health():
        return {'app': 'MangaStudio', 'ok': True, 'engine_version': ENGINE_VERSION}

    @app.get('/api/projects')
    def projects():
        return [{**p, 'chapters': len(store.list('chapters', p['id']))} for p in store.list('projects')]

    @app.post('/api/import')
    async def upload_book(file: UploadFile = File(...)):
        data = await read_upload(file, 25*1024*1024)
        try:
            return import_book(store, file.filename or 'Buch.docx', data)
        except Exception as exc:
            from .vendor.uploads import UploadError
            if isinstance(exc, UploadError):
                raise HTTPException(exc.status, str(exc)) from None
            raise

    @app.get('/api/deleted-projects')
    def deleted_projects():
        return store.archived_projects()

    @app.delete('/api/projects/{ident}')
    def delete_project(ident: str):
        return store.archive_project(ident)

    @app.post('/api/projects/{ident}/restore')
    def restore_project(ident: str):
        return store.archive_project(ident,restore=True)

    @app.get('/api/projects/{ident}')
    def project(ident: str):
        value = store.get('projects', ident)
        value['characters'] = store.list('characters', ident)
        value['deleted_characters'] = [{'id': item['character']['id'], 'name': item['character']['name']}
                                       for item in store.deleted_characters(ident)]
        value['chapters'] = [{key: chapter[key] for key in ('id', 'title', 'position', 'revision', 'summary')}
                             | {'scenes': len(chapter['scenes']), 'panels': sum(len(s['panels']) for s in chapter['scenes']),
                                'images': sum(bool(p.get('image')) for s in chapter['scenes'] for p in s['panels'])}
                             for chapter in store.list('chapters', ident)]
        value['jobs'] = store.jobs(ident)
        if value.get('style_draft'):
            value['style_draft_stale'] = value['style_draft']['source_signature'] != book_source_signature(store,value)
        return value

    @app.post('/api/projects/{ident}/style-analysis')
    def style_analysis(ident: str):
        idle(ident)
        value = store.get('projects',ident)
        if not style_parts(store,ident):raise ValueError('Dieses Buch enthält noch keinen analysierbaren Text.')
        return {'job_id':store.enqueue(ident,None,'book_style',{
            'source_signature':book_source_signature(store,value),'base_style':value['style']})}

    @app.put('/api/projects/{ident}')
    def project_settings(ident: str, settings: BookSettings):
        idle(ident)
        value = store.get('projects', ident)
        value.update(settings.model_dump())
        store.write('projects', value)
        return value

    @app.post('/api/projects/{ident}/characters')
    async def character_create(ident: str, name: str = Form(...), description: str = Form(...),
                               aliases: str = Form(''), file: UploadFile | None = File(None),
                               render_file: UploadFile | None = File(None)):
        idle(ident)
        store.get('projects', ident)
        value = CharacterInput(name=name, description=description, aliases=aliases).model_dump()
        value.update(id=uid(), image='')
        if file and file.filename:
            value['image'] = save_image(await read_upload(file, 15*1024*1024), ident, 'characters')
        if render_file and render_file.filename:
            value['render_source'] = save_image(await read_upload(render_file, 15*1024*1024), ident, 'character-renders')
        store.write('characters', value, ident)
        if value.get('render_source'):
            job_id = enqueue_character_render(ident, value, value['render_source'])
            return {**value, 'job_id': job_id}
        return value

    @app.put('/api/projects/{ident}/characters/{character_id}')
    def character_edit(ident: str, character_id: str, changes: CharacterInput):
        idle(ident)
        if character_id not in {c['id'] for c in store.list('characters', ident)}:
            raise HTTPException(404, 'Charakter nicht gefunden.')
        value = store.get('characters', character_id)
        value.update(changes.model_dump())
        store.write('characters', value, ident)
        return value

    @app.delete('/api/projects/{ident}/characters/{character_id}')
    def character_delete(ident: str, character_id: str):
        idle(ident)
        return store.remove_character(ident, character_id)

    @app.post('/api/projects/{ident}/characters/{character_id}/restore')
    def character_restore(ident: str, character_id: str):
        idle(ident)
        return store.restore_character(ident, character_id)

    @app.post('/api/chapters/{ident}/characters/autoadd')
    def characters_autoadd(ident: str):
        chapter = chapter_of(ident)
        if not chapter['text'].strip():
            raise ValueError('Das aktuelle Kapitel enthält keinen Text.')
        return {'job_id': store.enqueue(chapter['project_id'], ident, 'character_autoadd', {})}

    @app.post('/api/projects/{ident}/characters/{character_id}/image')
    async def character_image(ident: str, character_id: str, file: UploadFile = File(...)):
        idle(ident)
        if character_id not in {c['id'] for c in store.list('characters', ident)}:
            raise HTTPException(404, 'Charakter nicht gefunden.')
        value = store.get('characters', character_id)
        value['image'] = save_image(await read_upload(file, 15*1024*1024), ident, 'characters')
        store.write('characters', value, ident)
        return value

    @app.post('/api/projects/{ident}/characters/{character_id}/render')
    async def character_render(ident: str, character_id: str, file: UploadFile = File(...)):
        idle(ident)
        value = owned_character(ident, character_id)
        source = save_image(await read_upload(file, 15*1024*1024), ident, 'character-renders')
        job_id = enqueue_character_render(ident, value, source)
        value['render_source'] = source
        store.write('characters', value, ident)
        return {'character': value, 'job_id': job_id}

    @app.post('/api/projects/{ident}/characters/{character_id}/render/regenerate')
    def character_render_again(ident: str, character_id: str):
        idle(ident)
        value = owned_character(ident, character_id)
        if not value.get('render_source') or not store.asset(value['render_source']).is_file():
            raise ValueError('Bitte zuerst einen bestehenden Charakterrender hochladen.')
        return {'job_id': enqueue_character_render(ident, value, value['render_source'])}

    @app.post('/api/projects/{ident}/characters/{character_id}/generate')
    def character_generate(ident: str, character_id: str):
        idle(ident)
        value = owned_character(ident, character_id)
        if not value['description'].strip():
            raise ValueError('Bitte zuerst das Aussehen des Charakters beschreiben.')
        project = store.get('projects', ident)
        return {'job_id': store.enqueue(ident, None, 'character_generate', {
            'character_id': character_id, 'name': value['name'],
            'description': value['description'], 'style': project['style']})}

    @app.post('/api/projects/{ident}/characters/{character_id}/render/accept')
    def character_render_accept(ident: str, character_id: str, options: AcceptCharacterRender):
        idle(ident)
        value = owned_character(ident, character_id)
        draft = value.get('manga_draft')
        if not draft or draft.get('image') != options.image:
            raise HTTPException(409, 'Dieser Manga-Entwurf ist nicht mehr aktuell. Charakterprofil neu öffnen.')
        if not store.asset(draft['image']).is_file():
            raise ValueError('Das erzeugte Manga-Bild wurde nicht gefunden.')
        value['image'] = draft['image']
        if options.use_description:
            if not draft.get('analysis'):
                raise ValueError('Dieser Entwurf basiert auf deiner Beschreibung und enthält keine neue Bildanalyse.')
            value['description'] = draft['analysis']['description']
        store.write('characters', value, ident)
        return value

    @app.get('/api/chapters/{ident}')
    def chapter_get(ident: str):
        chapter = chapter_of(ident)
        project = store.get('projects', chapter['project_id'])
        characters = store.list('characters', project['id'])
        settings = store.settings()
        context=context_for(store,chapter,project)
        pages=pages_for_chapter(chapter,project['direction'],context['start_page'])
        panel_boxes={p['id']:p['box'] for page in pages for p in page['panels']}
        return {**chapter, 'dramaturgy_review': review_state(chapter), 'page_flow':flow_state(chapter,context),
                'pages':pages,'page_spreads':spreads(pages,project['direction'],context['previous_page'],context['following_page']),
                'stale_panels': [p['id'] for s in chapter['scenes'] for p in s['panels'] if p.get('image')
                                 and (p.get('image_signature') != image_signature(project, p, characters, settings)
                                      or not image_is_print_ready(store,p,panel_boxes[p['id']]))],
                'source_paragraphs': [{'number': i, 'text': text} for part in chunks(chapter['text']) for i, text in part]}

    @app.put('/api/chapters/{ident}/plan')
    def chapter_edit(ident: str, changes: EditPlan):
        chapter = chapter_of(ident)
        idle(chapter['project_id'])
        if changes.revision != chapter['revision']:
            raise HTTPException(409, 'Der Kapitelstand wurde geändert. Neu laden, damit keine Änderungen verloren gehen.')
        source = [row for part in chunks(chapter['text']) for row in part]
        allowed = {c['id'] for c in store.list('characters', chapter['project_id'])}
        ids = [p.id for s in changes.scenes for p in s.panels]
        scene_ids = [s.id for s in changes.scenes]
        if len(ids) != len(set(ids)) or len(scene_ids) != len(set(scene_ids)):
            raise ValueError('Szenen- und Panel-IDs müssen eindeutig sein.')
        old = {p['id']: p for s in chapter['scenes'] for p in s['panels']}
        for scene in changes.scenes:
            validate_chunk(PlanChunk(summary='Manuell bearbeitet', scenes=[scene]), source, allowed)
            for panel in scene.panels:
                existing = old.get(panel.id, {})
                panel.image = existing.get('image', '')
                panel.image_signature = existing.get('image_signature', '')
        chapter['scenes'] = [s.model_dump() for s in changes.scenes]
        if not chapter['scenes']:
            chapter['summary'] = ''
        chapter['revision'] += 1
        save_chapter(chapter)
        return chapter_get(ident)

    @app.post('/api/chapters/{ident}/preview')
    def chapter_preview(ident: str, changes: EditPlan):
        chapter = chapter_of(ident)
        project = store.get('projects', chapter['project_id'])
        preview = {**chapter, 'scenes': [s.model_dump() for s in changes.scenes]}
        context=context_for(store,chapter,project)
        pages=pages_for_chapter(preview,project['direction'],context['start_page'])
        return {'pages':pages,'page_spreads':spreads(pages,project['direction'],context['previous_page'],context['following_page'])}

    @app.post('/api/chapters/{ident}/page-flow')
    def page_flow_start(ident: str):
        chapter=chapter_of(ident);project=store.get('projects',chapter['project_id'])
        if not chapter['scenes']:raise ValueError('Zuerst ein Storyboard anlegen.')
        context=context_for(store,chapter,project)
        return {'job_id':store.enqueue(project['id'],ident,'page_flow',{
            'story_signature':story_signature(chapter),'context_signature':context['signature']})}

    @app.get('/api/chapters/{ident}/page-flow')
    def page_flow_get(ident: str):
        chapter=chapter_of(ident);project=store.get('projects',chapter['project_id'])
        return preview_flow(store,chapter,project)

    @app.post('/api/chapters/{ident}/page-flow/preview')
    def page_flow_preview(ident: str,plan: FlowPlan):
        chapter=chapter_of(ident);project=store.get('projects',chapter['project_id'])
        return preview_flow(store,chapter,project,plan)

    @app.post('/api/chapters/{ident}/page-flow/decide')
    def page_flow_decide(ident: str,decision: FlowDecision):
        chapter=chapter_of(ident);project=store.get('projects',chapter['project_id'])
        idle(project['id'])
        try:decide_flow(store,chapter,project,decision)
        except ValueError as exc:raise HTTPException(409,str(exc)) from None
        return chapter_get(ident)

    @app.post('/api/chapters/{ident}/page-flow/edit')
    def page_flow_edit(ident: str):
        chapter=chapter_of(ident);idle(chapter['project_id'])
        edit_active_flow(store,ident)
        return chapter_get(ident)

    @app.post('/api/chapters/{ident}/layout')
    def layout_start(ident: str):
        chapter = chapter_of(ident)
        if not chapter['scenes']:
            raise ValueError('Zuerst ein Storyboard anlegen.')
        return {'job_id': store.enqueue(chapter['project_id'], ident, 'layout', {'revision': chapter['revision']})}

    @app.post('/api/chapters/{ident}/dramaturgy')
    def dramaturgy_start(ident: str):
        chapter = chapter_of(ident)
        if not chapter['scenes']:
            raise ValueError('Zuerst ein Storyboard anlegen.')
        return {'job_id': store.enqueue(chapter['project_id'], ident, 'dramaturgy', {'story_signature': story_signature(chapter)})}

    @app.post('/api/chapters/{ident}/dramaturgy/{finding_id}')
    def dramaturgy_decide(ident: str, finding_id: str, decision: ReviewDecision):
        chapter = chapter_of(ident)
        idle(chapter['project_id'])
        try:
            decide_suggestion(store, ident, decision, finding_id)
        except ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from None
        return chapter_get(ident)

    @app.post('/api/chapters/{ident}/plan')
    def plan_start(ident: str, options: PlanRequest):
        chapter = chapter_of(ident)
        if chapter['scenes'] and not options.replace:
            raise HTTPException(409, 'Ein Storyboard existiert bereits. Ersetzen muss ausdrücklich gewählt werden.')
        job = store.enqueue(chapter['project_id'], ident, 'plan', {})
        return {'job_id': job}

    @app.post('/api/chapters/{ident}/images')
    def images_start(ident: str, options: GenerateRequest):
        chapter = chapter_of(ident)
        if not chapter['scenes']:
            raise ValueError('Zuerst ein Storyboard anlegen.')
        if options.panel_id and options.panel_id not in {p['id'] for s in chapter['scenes'] for p in s['panels']}:
            raise ValueError('Panel nicht gefunden.')
        job = store.enqueue(chapter['project_id'], ident, 'images', options.model_dump())
        return {'job_id': job}

    @app.post('/api/chapters/{ident}/poses')
    def poses_start(ident: str, options: GenerateRequest):
        chapter = chapter_of(ident)
        panels = [p for scene in chapter['scenes'] for p in scene['panels']]
        if options.panel_id and options.panel_id not in {p['id'] for p in panels}:
            raise HTTPException(404, 'Panel nicht gefunden.')
        if not any(p['characters'] for p in panels if not options.panel_id or p['id'] == options.panel_id):
            raise ValueError('Zuerst Charaktere den Panels zuordnen.')
        return {'job_id': store.enqueue(chapter['project_id'], ident, 'poses',
            {**options.model_dump(), 'revision': chapter['revision']})}

    @app.post('/api/chapters/{ident}/panels/{panel_id}/image')
    async def panel_upload(ident: str, panel_id: str, file: UploadFile = File(...)):
        chapter = chapter_of(ident)
        idle(chapter['project_id'])
        panel = next((p for s in chapter['scenes'] for p in s['panels'] if p['id'] == panel_id), None)
        if panel is None:
            raise HTTPException(404, 'Panel nicht gefunden.')
        panel['image'] = save_image(await read_upload(file, 15*1024*1024), chapter['project_id'], 'panels')
        panel['image_signature'] = image_signature(store.get('projects', chapter['project_id']), panel,
                                store.list('characters', chapter['project_id']), store.settings())
        chapter['revision'] += 1
        save_chapter(chapter)
        return chapter_get(ident)

    @app.get('/api/jobs')
    def jobs():
        return store.jobs()

    @app.post('/api/jobs/{ident}/retry')
    def retry(ident: str):
        job = store.job(ident)
        idle(job['project_id'])
        if job['state'] != 'failed':
            raise ValueError('Nur fehlgeschlagene Aufträge können fortgesetzt werden.')
        store.update_job(ident, state='queued', message='Fortsetzung vorgemerkt')
        return {'job_id': ident}

    @app.get('/api/settings')
    def get_settings():
        return store.settings().model_dump()

    @app.put('/api/settings')
    def put_settings(settings: Settings):
        if any(j['state'] in ('running', 'queued') for j in store.jobs()):
            raise HTTPException(409, 'Während eines Auftrags keine Verbindungseinstellungen ändern.')
        parsed = urlsplit(settings.comfy_url)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.path not in ('', '/') or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('Diese Version unterstützt ausschließlich lokales ComfyUI per HTTP auf localhost.')
        if 'flux-2-klein' not in settings.image_model or 'base' in settings.image_model:
            raise ValueError('Der vorbereitete Bildflow benötigt Flux.2 Klein Distilled (4B oder 9B).')
        store.save_settings(settings)
        return settings

    @app.get('/api/connection')
    def connection():
        settings = store.settings()
        client = ComfyClient(settings.comfy_url)
        try:
            client.check()
            info = client.transport.get_json(settings.comfy_url.rstrip('/')+'/object_info')
            def options(node, inp):
                val = info.get(node, {}).get('input', {}).get('required', {}).get(inp, [[]])[0]
                if isinstance(val, list):
                    return val
                return info.get(node, {}).get('input', {}).get('required', {}).get(inp, [None, {}])[1].get('options', [])
            required = ['TextGenerate', 'PreviewAny', 'UNETLoader', 'CLIPLoader', 'ReferenceLatent', 'Flux2Scheduler', 'EmptyFlux2LatentImage']
            missing = [node for node in required if node not in info]
            unets, clips, vaes = options('UNETLoader', 'unet_name'), options('CLIPLoader', 'clip_name'), options('VAELoader', 'vae_name')
            selected = [('Bildmodell', settings.image_model, unets), ('Textmodell', settings.text_model, clips),
                        ('Bildanalyse-Modell', settings.vision_model, clips),
                        ('Bildencoder', settings.image_encoder, clips), ('VAE', settings.image_vae, vaes)]
            missing_models = [label+': '+name for label, name, choices in selected if name not in choices]
            return {'connected': True, 'ready': not missing and not missing_models, 'missing_nodes': missing,
                    'missing_models': missing_models, 'image_models': [m for m in unets if 'flux-2-klein' in m and 'base' not in m],
                    'text_models': clips, 'vaes': vaes}
        except Exception:
            return {'connected': False, 'ready': False, 'message': 'ComfyUI nicht erreichbar. Comfy Desktop starten und die lokale Adresse prüfen.'}

    @app.post('/api/projects/{ident}/export')
    def export(ident: str, options: ExportRequest):
        idle(ident)
        project = store.get('projects', ident)
        chapters = store.list('chapters', ident)
        if not options.draft and any(not c['scenes'] for c in chapters):
            raise ValueError('Nicht alle Kapitel besitzen ein Storyboard. Für einen Teilstand bitte Layout-Entwurf wählen.')
        if not options.draft:
            cast, settings = store.list('characters', ident), store.settings()
            if any(p.get('image_signature') != image_signature(project, p, cast, settings) for c in chapters for s in c['scenes'] for p in s['panels']):
                raise ValueError('Einige Panelbilder fehlen oder passen nicht mehr zum aktuellen Prompt/Charakterstand. Bilder aktualisieren oder Entwurf exportieren.')
            if any(not image_is_print_ready(store,p,p['box']) for page in book_pages(chapters,project['direction']) for p in page['panels']):
                raise ValueError('Einige Panelbilder sind für ihre Druckgröße bei 300 dpi zu klein. Bilder neu erzeugen oder einen Layout-Entwurf exportieren.')
        relative = f'books/{ident}/exports/{uid()}{"-entwurf" if options.draft else "-manga"}.pdf'
        count = export_pdf(store, project, chapters, store.asset(relative), options.draft)
        value = {'path': relative, 'pages': count, 'draft': options.draft}
        project.setdefault('exports', []).append(value)
        store.write('projects', project)
        return value

    @app.get('/assets/{relative:path}')
    def asset(relative: str):
        path = store.asset(relative)
        if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.pdf'} or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.post('/api/demo')
    def demo():
        from .demo import create_demo
        return create_demo(store)

    return app


app = create_app()
