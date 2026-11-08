"""Local text documents with transactional versions, journal and compare-and-swap.

No shell, executable files, arbitrary paths, network or model callbacks. This is
an application boundary, not isolation from another process under the same user.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from itertools import islice

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 64 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def check_local(source):
    if source not in ('text', 'voice'):
        raise ValueError('protected_local_request_required')


def checked_name(name):
    if (type(name) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,63}\.txt', name)
            or name[:-4].endswith(' ')
            or name[:-4].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(10)),
                                    *(f'LPT{i}' for i in range(10))}):
        raise ValueError('protected_text_filename_required')
    return name.lower()


def checked_body(body):
    if type(body) is not str or '\x00' in body or len(body.encode('utf-8')) > MAX_BODY:
        raise ValueError('protected_document_size_or_format')
    return body


def digest(body):
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def reject_links(path):
    """Reject existing redirections and multi-link files before opening storage."""
    for node in (path, *path.parents):
        if node.exists() or node.is_symlink():
            info = node.lstat()
            if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
                raise ValueError('protected_link_refused')


class Workspace:
    def __init__(self, directory=None):
        self.directory = Path(directory or ROOT/'data/protected_workspace').absolute()
        allowed = ROOT/'data/protected_workspace'
        if self.directory != allowed:
            try:
                relative = self.directory.relative_to(ROOT/'data/validation')
            except ValueError:
                raise ValueError('protected_storage_outside_scope') from None
            if not relative.parts or not relative.parts[0].startswith('validation_'):
                raise ValueError('protected_validation_directory_required')
        if '..' in self.directory.parts:
            raise ValueError('protected_storage_outside_scope')

    @contextmanager
    def database(self, cancelled=lambda:False):
        reject_links(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory/'documents.sqlite3'
        for suffix in ('', '-journal', '-wal', '-shm'):
            reject_links(Path(str(path)+suffix))
        db = sqlite3.connect(path, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS revisions '
                       '(id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL, '
                       'hash TEXT NOT NULL, created REAL NOT NULL, reason TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS documents (name TEXT PRIMARY KEY, revision TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events '
                       '(id INTEGER PRIMARY KEY, created REAL NOT NULL, action TEXT NOT NULL, '
                       'name TEXT NOT NULL, revision TEXT NOT NULL)')
            if cancelled():raise ValueError('protected_cancelled')
            yield db
            if cancelled():raise ValueError('protected_cancelled')
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    @staticmethod
    def _read(db, name):
        row = db.execute('SELECT r.* FROM documents d JOIN revisions r ON r.id=d.revision '
                         'WHERE d.name=?', (name,)).fetchone()
        if row is None:
            return None
        if digest(row['body']) != row['hash']:
            raise ValueError('protected_revision_corrupt')
        return dict(row)

    def read(self, name, *, source):
        check_local(source); name = checked_name(name)
        with self.database() as db:
            return self._read(db, name)

    def list(self, *, source):
        check_local(source)
        with self.database() as db:
            return [row[0] for row in db.execute('SELECT name FROM documents ORDER BY name LIMIT 100')]

    @staticmethod
    def _write(db, name, body, expected, reason):
        current = Workspace._read(db, name)
        if (current['id'] if current else None) != expected:
            raise ValueError('protected_document_changed')
        if current and current['body'] == body:
            return current['id']
        total = db.execute('SELECT coalesce(sum(length(CAST(body AS BLOB))),0) FROM revisions').fetchone()[0]
        count = db.execute('SELECT count(*) FROM revisions').fetchone()[0]
        if total + len(body.encode('utf-8')) > MAX_TOTAL or count >= 5000:
            raise ValueError('protected_history_full')
        revision = uuid.uuid4().hex
        now = time.time()
        db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?)',
                   (revision, name, body, digest(body), now, reason))
        db.execute('INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision',
                   (name, revision))
        db.execute('INSERT INTO events(created,action,name,revision) VALUES (?,?,?,?)',
                   (now, reason, name, revision))
        return revision

    def write(self, name, body, *, source, expected=None, cancelled=lambda:False):
        check_local(source); name = checked_name(name); body = checked_body(body)
        with self.database(cancelled) as db:
            return self._write(db, name, body, expected, 'modifier' if expected else 'creer')

    def history(self, name, *, source):
        check_local(source); name = checked_name(name)
        with self.database() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,created,reason,hash FROM revisions WHERE name=? ORDER BY rowid DESC LIMIT 100', (name,))]

    def restore(self, name, revision, *, source, expected, cancelled=lambda:False):
        check_local(source); name = checked_name(name)
        with self.database(cancelled) as db:
            row = db.execute('SELECT body,hash FROM revisions WHERE name=? AND id=?', (name, revision)).fetchone()
            if row is None or digest(row['body']) != row['hash']:
                raise ValueError('protected_revision_missing_or_corrupt')
            return self._write(db, name, row['body'], expected, 'restaurer')

    def journal(self, *, source):
        check_local(source)
        with self.database() as db:
            return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]

    def export(self, name, *, source):
        """Exclusive numbered .txt export in the owned directory, never overwrite."""
        check_local(source); name = checked_name(name)
        with self.database() as db:
            row = self._read(db, name)
            if row is None:
                raise ValueError('protected_document_missing')
            folder = self.directory/'exports'
            reject_links(folder); folder.mkdir(exist_ok=True)
            exports=list(islice(folder.iterdir(),501))
            if len(exports)>=500:
                raise ValueError('protected_export_quota')
            for path in exports:
                reject_links(path)
                if not path.is_file():raise ValueError('protected_export_directory_changed')
            if sum(path.stat().st_size for path in exports)+len(row['body'].encode('utf-8'))>MAX_TOTAL:
                raise ValueError('protected_export_quota')
            target = folder/(uuid.uuid4().hex+'_'+name)
            with target.open('x', encoding='utf-8', newline='') as stream:
                stream.write(row['body']); stream.flush(); os.fsync(stream.fileno())
            with target.open(encoding='utf-8', newline='') as stream:
                verified = stream.read() == row['body']
            if not verified:
                raise ValueError('protected_export_unverified')
            db.execute('INSERT INTO events(created,action,name,revision) VALUES (?,?,?,?)',
                       (time.time(), 'exporter', name, row['id']))
            return target

    def import_text(self, name, *, source):
        """Import a user-deposited UTF-8 text copy, never an arbitrary host path."""
        check_local(source); name=checked_name(name)
        folder=self.directory/'imports'
        reject_links(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/name
        reject_links(path)
        if not path.is_file() or path.stat().st_size>MAX_BODY:
            raise ValueError('protected_import_missing_or_large')
        with path.open('rb') as stream:
            content=stream.read(MAX_BODY+1)
        if len(content)>MAX_BODY:raise ValueError('protected_import_too_large')
        body=checked_body(content.decode('utf-8-sig'))
        with self.database() as db:
            return self._write(db,name,body,None,'importer')
