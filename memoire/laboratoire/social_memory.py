"""Bounded raw public exchanges, isolated by verified platform identity."""
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path


class PublicMemory:
    def __init__(self, database, identity, *, allow_public=False, clock=time.time):
        if not identity.startswith('validation_') and not (allow_public and identity == 'public_channels'):
            raise ValueError('Explicit public or validation storage required')
        self.clock = clock
        path = Path(database)
        # Production and validation must never share a file, even by accident.
        if path.stem != identity:
            raise ValueError('Database must match its isolated identity')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('CREATE TABLE IF NOT EXISTS public (source TEXT, author TEXT, seen REAL, greeted TEXT, turns TEXT, PRIMARY KEY(source,author))')
        self.prune()

    def prune(self):
        with self.db:
            self.db.execute('DELETE FROM public WHERE seen < ?', (self.clock()-180*86400,))
            self.db.execute('DELETE FROM public WHERE rowid NOT IN (SELECT rowid FROM public ORDER BY seen DESC,rowid DESC LIMIT 1000)')

    def today(self):
        return datetime.fromtimestamp(self.clock()).date().isoformat()

    def context(self, source, author):
        if source not in {'twitch', 'discord'} or not isinstance(author,str) or not 1 <= len(author) <= 80:
            raise ValueError('Invalid public identity')
        self.prune()
        row = self.db.execute('SELECT greeted,turns FROM public WHERE source=? AND author=?', (source,author)).fetchone()
        return (json.loads(row[1]) if row else []), bool(row and row[0] == self.today())

    def record(self, source, author, text, reply):
        turns, _ = self.context(source, author)
        turns += [{'role':'user','content':text[:2000]}, {'role':'assistant','content':reply[:600]}]
        # Preserve whole pairs, their context and ordering; no inferred permanent facts.
        while len(turns) > 24 or sum(len(t['content']) for t in turns) > 6000:
            turns = turns[2:]
        with self.db:
            self.db.execute('INSERT INTO public VALUES(?,?,?,?,?) ON CONFLICT(source,author) DO UPDATE SET seen=excluded.seen,turns=excluded.turns',
                (source,author,self.clock(),'',json.dumps(turns,ensure_ascii=False)))
        self.prune()

    def delivered(self, source, author):
        with self.db:
            self.db.execute('UPDATE public SET greeted=? WHERE source=? AND author=?', (self.today(),source,author))

    def forget(self, source, author):
        with self.db:
            self.db.execute('DELETE FROM public WHERE source=? AND author=?', (source,author))

    def close(self):
        self.db.close()
