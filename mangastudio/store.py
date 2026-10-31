"""SQLite metadata and bounded local assets; no access to the promotion database."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
from .models import Settings, uid

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MANGA_DATA_DIR', ROOT / 'data')).resolve()


class Store:
    def __init__(self, root=DATA):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'manga.sqlite3'
        with self.connect() as con:
            con.executescript('''
                pragma journal_mode=WAL;
                create table if not exists projects(id text primary key, data text not null);
                create table if not exists chapters(id text primary key, project_id text not null, position integer not null, data text not null);
                create table if not exists characters(id text primary key, project_id text not null, data text not null);
                create table if not exists character_trash(id text primary key, project_id text not null,
                    data text not null, deleted real not null);
                create table if not exists settings(id integer primary key, data text not null);
                create table if not exists jobs(id text primary key, project_id text not null, chapter_id text,
                    kind text not null, state text not null, message text not null, progress real not null,
                    payload text not null, created real not null);
            ''')
            con.execute('insert or ignore into settings values(1,?)', (json.dumps(Settings().model_dump()),))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=20)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def asset(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError('Ungültiger Dateipfad.')
        return path

    def write(self, table, value, project_id=None, position=None):
        if table not in {'projects', 'chapters', 'characters'}:
            raise ValueError(table)
        with self.connect() as con:
            if table == 'projects':
                con.execute('insert or replace into projects values(?,?)', (value['id'], json.dumps(value, ensure_ascii=False)))
            elif table == 'chapters':
                con.execute('insert or replace into chapters values(?,?,?,?)', (value['id'], project_id, position, json.dumps(value, ensure_ascii=False)))
            else:
                con.execute('insert or replace into characters values(?,?,?)', (value['id'], project_id, json.dumps(value, ensure_ascii=False)))

    def get(self, table, ident):
        if table not in {'projects', 'chapters', 'characters'}:
            raise ValueError(table)
        with self.connect() as con:
            row = con.execute(f'select data from {table} where id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError('Eintrag wurde nicht gefunden.')
        value = json.loads(row['data'])
        if table == 'projects' and value.get('archived_at'):
            raise KeyError('Dieses Buch wurde gelöscht. Unter „Gelöschte Bücher“ wiederherstellen.')
        return value

    def list(self, table, project_id=None):
        if table not in {'projects', 'chapters', 'characters'}:
            raise ValueError(table)
        query = f'select data from {table}'
        values = ()
        if project_id is not None:
            query += ' where project_id=?'
            values = (project_id,)
        query += ' order by position' if table == 'chapters' else ' order by rowid'
        with self.connect() as con:
            result = [json.loads(row['data']) for row in con.execute(query, values)]
        return [item for item in result if not item.get('archived_at')] if table == 'projects' else result

    def archived_projects(self):
        with self.connect() as con:
            items = [json.loads(row['data']) for row in con.execute('select data from projects')]
        return sorted([{'id':p['id'],'title':p['title'],'archived_at':p['archived_at']}
                       for p in items if p.get('archived_at')],key=lambda p:p['archived_at'],reverse=True)

    def archive_project(self,ident,restore=False):
        with self.connect() as con:
            con.execute('begin immediate')
            row = con.execute('select data from projects where id=?',(ident,)).fetchone()
            if row is None:raise KeyError('Buch nicht gefunden.')
            if con.execute("select 1 from jobs where project_id=? and state in ('queued','running')",(ident,)).fetchone():
                raise ValueError('Für dieses Buch läuft ein Auftrag. Bitte danach löschen oder wiederherstellen.')
            value = json.loads(row['data'])
            if restore:value.pop('archived_at',None)
            else:value.setdefault('archived_at',time.time())
            con.execute('update projects set data=? where id=?',(json.dumps(value,ensure_ascii=False),ident))
        return {'id':ident,'title':value['title'],'recoverable':True}

    def settings(self):
        with self.connect() as con:
            return Settings.model_validate_json(con.execute('select data from settings where id=1').fetchone()['data'])

    def save_settings(self, value):
        with self.connect() as con:
            con.execute('update settings set data=? where id=1', (value.model_dump_json(),))

    def deleted_characters(self, project_id):
        with self.connect() as con:
            return [json.loads(row['data']) for row in con.execute(
                'select data from character_trash where project_id=? order by deleted desc', (project_id,))]

    def remove_character(self, project_id, character_id):
        with self.connect() as con:
            con.execute('begin immediate')
            if con.execute("select 1 from jobs where project_id=? and state in ('queued','running')", (project_id,)).fetchone():
                raise ValueError('Während eines laufenden Buchauftrags kann kein Charakter entfernt werden.')
            row = con.execute('select rowid as original_rowid,data from characters where id=? and project_id=?', (character_id, project_id)).fetchone()
            if row is None:
                raise KeyError('Charakter nicht gefunden.')
            character = json.loads(row['data'])
            original_rowid = row['original_rowid']
            links = []
            for row in con.execute('select id,data from chapters where project_id=?', (project_id,)).fetchall():
                chapter = json.loads(row['data'])
                changed = False
                for scene in chapter['scenes']:
                    for panel in scene['panels']:
                        if character_id in panel['characters']:
                            links.append({'chapter_id': chapter['id'], 'panel_id': panel['id'], 'index': panel['characters'].index(character_id),
                                          'pose': panel.get('character_poses', {}).get(character_id, '')})
                            panel.get('character_poses', {}).pop(character_id, None)
                            panel['characters'] = [ident for ident in panel['characters'] if ident != character_id]
                            changed = True
                if changed:
                    chapter['revision'] += 1
                    con.execute('update chapters set data=? where id=?', (json.dumps(chapter, ensure_ascii=False), chapter['id']))
            archived = {'character': character, 'panel_links': links, 'original_rowid': original_rowid}
            con.execute('insert into character_trash values(?,?,?,?)',
                        (character_id, project_id, json.dumps(archived, ensure_ascii=False), time.time()))
            con.execute('delete from characters where id=? and project_id=?', (character_id, project_id))
        return {'id': character_id, 'name': character['name'], 'affected_panels': len(links), 'recoverable': True}

    def restore_character(self, project_id, character_id):
        with self.connect() as con:
            con.execute('begin immediate')
            if con.execute("select 1 from jobs where project_id=? and state in ('queued','running')", (project_id,)).fetchone():
                raise ValueError('Während eines laufenden Buchauftrags kann kein Charakter wiederhergestellt werden.')
            row = con.execute('select data from character_trash where id=? and project_id=?', (character_id, project_id)).fetchone()
            if row is None:
                raise KeyError('Gelöschter Charakter nicht gefunden.')
            archived = json.loads(row['data'])
            character = archived['character']
            original_rowid = archived.get('original_rowid')
            if original_rowid is not None and con.execute('select 1 from characters where rowid=?', (original_rowid,)).fetchone() is None:
                con.execute('insert into characters(rowid,id,project_id,data) values(?,?,?,?)',
                            (original_rowid, character_id, project_id, json.dumps(character, ensure_ascii=False)))
            else:
                con.execute('insert into characters values(?,?,?)', (character_id, project_id, json.dumps(character, ensure_ascii=False)))
            by_chapter = {}
            for link in archived['panel_links']:
                by_chapter.setdefault(link['chapter_id'], []).append(link)
            for chapter_id, links in by_chapter.items():
                row = con.execute('select data from chapters where id=? and project_id=?', (chapter_id, project_id)).fetchone()
                if row is None:
                    continue
                chapter = json.loads(row['data'])
                panels = {p['id']: p for s in chapter['scenes'] for p in s['panels']}
                changed = False
                for link in links:
                    panel = panels.get(link['panel_id'])
                    if panel and character_id not in panel['characters'] and len(panel['characters']) < 4:
                        panel['characters'].insert(min(link['index'], len(panel['characters'])), character_id)
                        if link.get('pose'):
                            panel.setdefault('character_poses', {})[character_id] = link['pose']
                        changed = True
                if changed:
                    chapter['revision'] += 1
                    con.execute('update chapters set data=? where id=?', (json.dumps(chapter, ensure_ascii=False), chapter_id))
            con.execute('delete from character_trash where id=? and project_id=?', (character_id, project_id))
        return character

    def busy(self, project_id):
        with self.connect() as con:
            return con.execute("select 1 from jobs where project_id=? and state in ('queued','running')", (project_id,)).fetchone() is not None

    def enqueue(self, project_id, chapter_id, kind, payload=None):
        ident = uid()
        with self.connect() as con:
            con.execute('begin immediate')
            project = con.execute('select data from projects where id=?',(project_id,)).fetchone()
            if project is None or json.loads(project['data']).get('archived_at'):
                raise KeyError('Buch nicht gefunden oder gelöscht.')
            if con.execute("select 1 from jobs where project_id=? and state in ('queued','running')", (project_id,)).fetchone():
                raise ValueError('Für dieses Buch läuft bereits ein Auftrag.')
            con.execute('insert into jobs values(?,?,?,?,?,?,?,?,?)',
                        (ident, project_id, chapter_id, kind, 'queued', 'Wartet', 0, json.dumps(payload or {}), time.time()))
        return ident

    def jobs(self, project_id=None):
        with self.connect() as con:
            if project_id:
                rows = con.execute('select * from jobs where project_id=? order by created desc limit 30', (project_id,))
            else:
                rows = con.execute('select * from jobs order by created desc limit 30')
            return [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows]

    def job(self, ident):
        with self.connect() as con:
            row = con.execute('select * from jobs where id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError('Auftrag nicht gefunden.')
        return {**dict(row), 'payload': json.loads(row['payload'])}

    def update_job(self, ident, **values):
        allowed = {'payload', 'state', 'progress', 'message'}
        if set(values) - allowed:
            raise ValueError('Ungültige Jobfelder.')
        if 'payload' in values:
            values['payload'] = json.dumps(values['payload'], ensure_ascii=False)
        with self.connect() as con:
            con.execute('update jobs set ' + ','.join(f'{key}=?' for key in values) + ' where id=?', (*values.values(), ident))

    def recover(self):
        with self.connect() as con:
            con.execute("update jobs set state='queued',message='Nach Neustart fortsetzen' where state='running'")

    def claim(self):
        with self.connect() as con:
            con.execute('begin immediate')
            row = con.execute("select id from jobs where state='queued' order by created limit 1").fetchone()
            if row:
                con.execute("update jobs set state='running',message='Startet' where id=?", (row['id'],))
                return row['id']
