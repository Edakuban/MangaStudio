from pathlib import Path
import re
from uuid import uuid4
from .models import uid, BookSettings
from .vendor.extraction import extract_docx


def import_book(store, filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.docx', '.txt', '.md'}:
        raise ValueError('Bitte DOCX, TXT oder Markdown hochladen.')
    if not data or len(data) > 25 * 1024 * 1024:
        raise ValueError('Die Buchdatei ist leer oder größer als 25 MB.')
    project_id = uid()
    original = f'books/{project_id}/original{suffix}'
    path = store.asset(original)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    warnings = []
    if suffix == '.docx':
        extracted = extract_docx(path, str(uuid4()))
        chapters = [{'title': ch.title, 'text': ch.source_text} for ch in extracted.chapters]
        warnings = [w.message for w in extracted.warnings]
    else:
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = data.decode('cp1252')
        chapters = split_text(text)
    if not chapters or not any(ch['text'].strip() for ch in chapters):
        raise ValueError('Kein nutzbarer Buchtext gefunden.')
    project = {'id': project_id, **BookSettings(title=Path(filename).stem).model_dump(),
               'filename': Path(filename).name, 'original': original, 'warnings': warnings,
               'demo': False, 'exports': []}
    store.write('projects', project)
    for pos, ch in enumerate(chapters, 1):
        chapter = {'id': uid(), 'project_id': project_id, 'position': pos, 'title': ch['title'],
                   'text': ch['text'], 'scenes': [], 'revision': 0, 'summary': ''}
        store.write('chapters', chapter, project_id, pos)
    return project


def split_text(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    heading = re.compile(r'^(?:#{1,2}\s+.+|(?:Kapitel|Chapter)\s+\S+.*|(?:Prolog|Epilog|Prologue|Epilogue)(?:\s*[:\-].*)?)$', re.I)
    chapters, title, content = [], 'Kapitel 1', []
    for line in text.splitlines():
        if heading.match(line.strip()):
            if '\n'.join(content).strip():
                chapters.append({'title': title, 'text': '\n'.join(content).strip()})
            title, content = line.strip().lstrip('#').strip(), []
        else:
            content.append(line)
    if '\n'.join(content).strip():
        chapters.append({'title': title, 'text': '\n'.join(content).strip()})
    return chapters


def paragraphs(text):
    return [part.strip() for part in re.split(r'\n\s*\n', text.strip()) if part.strip()]


def chunks(text, limit=10000):
    """Never drop long paragraphs; sentence-sized subparagraphs receive stable indices."""
    expanded = []
    for paragraph in paragraphs(text):
        while len(paragraph) > limit:
            cut = paragraph.rfind(' ', 0, limit)
            cut = cut if cut > limit // 2 else limit
            expanded.append(paragraph[:cut])
            paragraph = paragraph[cut:].strip()
        expanded.append(paragraph)
    result, current, length = [], [], 0
    for number, paragraph in enumerate(expanded, 1):
        if current and length + len(paragraph) > limit:
            result.append(current)
            current, length = [], 0
        current.append((number, paragraph))
        length += len(paragraph) + 20
    if current:
        result.append(current)
    return result
