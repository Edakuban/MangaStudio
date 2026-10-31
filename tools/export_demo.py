"""Render a labelled six-page layout proof from synthetic demo content."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mangastudio.store import Store, ROOT
from mangastudio.demo import create_demo
from mangastudio.pdf_export import export_pdf

store = Store()
project = create_demo(store)
out = ROOT / 'output' / 'pdf' / 'manga-layout-demo.pdf'
pages = export_pdf(store, project, store.list('chapters', project['id']), out, draft=True)
print(f'{pages} pages: {out}')
