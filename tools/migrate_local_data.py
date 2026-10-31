"""Copy private assets and use SQLite's online backup for consistent metadata."""
from pathlib import Path
import shutil
import sqlite3
import sys

target = Path(__file__).resolve().parents[1] / 'data'
source = Path(sys.argv[1]).resolve() / 'data'
if target.exists():
    raise SystemExit('Destination data already exists; refusing to overwrite.')
target.mkdir(parents=True)
for path in source.iterdir():
    if path.name.startswith('manga.sqlite3'):
        continue
    if path.is_dir():
        shutil.copytree(path, target / path.name)
    else:
        shutil.copy2(path, target / path.name)
with sqlite3.connect((source / 'manga.sqlite3').as_uri()+'?mode=ro', uri=True) as origin:
    with sqlite3.connect(target / 'manga.sqlite3') as destination:
        origin.backup(destination)
print('Local assets copied; consistent SQLite backup completed. Original preserved.')
