"""Migration contracts, without models or access to personal storage."""
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
NAMES = ('memory_backend v5_context_memory episode_conversation persistent_memory '
         'local_memory_store episodic_memory reviewed_memory_reader memory_relevance '
         'memory_source_provenance memory_forgetting memory_response_format').split()


class Vector(list):
    """Tiny injected numeric double: no embedding library or model is imported."""
    ndim = 1
    @property
    def size(self): return len(self)
    @property
    def nbytes(self): return len(self) * 4
    def __truediv__(self, value): return Vector(x / value for x in self)
    def __matmul__(self, other): return sum(a * b for a, b in zip(self, other))
    def tobytes(self): return struct.pack('<' + 'f' * len(self), *self)


class FictionalSearch:
    np = SimpleNamespace(
        asarray=lambda v, **_: Vector(v),
        frombuffer=lambda b, **_: Vector(struct.unpack('<' + 'f' * (len(b) // 4), b)),
        isfinite=lambda v: SimpleNamespace(all=lambda: all(math.isfinite(x) for x in v)),
        linalg=SimpleNamespace(norm=lambda v: math.sqrt(sum(x * x for x in v))))
    def vector(self, text):
        return Vector([1., float('validation_old' in text), float('validation_new' in text)])


class PrivateCoreTests(unittest.TestCase):
    def setUp(self):
        validation = ROOT / 'data/validation'
        validation.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='validation_private_', dir=validation)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_each_entry_point_in_both_import_orders(self):
        # A fresh process for each module also detects partially initialized cycles.
        for name in NAMES:
            for canonical_first in (True, False):
                first = 'memoire.laboratoire.' + name if canonical_first else name
                second = name if canonical_first else 'memoire.laboratoire.' + name
                code = f'''import importlib, sys
import sqlite3
sqlite3.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('database at import'))
a = importlib.import_module({first!r})
b = importlib.import_module({second!r})
assert a is b
assert not any(n in sys.modules for n in ('fastembed', 'numpy', 'chat', 'voice_protocol'))
'''
                path = ROOT if canonical_first else ROOT / 'laboratoire/scripts'
                env = dict(os.environ, PYTHONPATH=str(path), PYTHONDONTWRITEBYTECODE='1')
                with self.subTest(name=name, canonical_first=canonical_first):
                    subprocess.run([sys.executable, '-B', '-c', code], cwd=self.folder,
                                   env=env, check=True, capture_output=True, text=True)

    def test_roots_and_factory_patch_survive(self):
        from memoire.laboratoire import memory_backend, persistent_memory, local_memory_store
        self.assertEqual(memory_backend.ROOT, ROOT / 'laboratoire')
        self.assertEqual(persistent_memory.ROOT, ROOT / 'laboratoire')
        self.assertEqual(local_memory_store.user_data('validation_path'),
                         ROOT / 'laboratoire/data/memory/validation_path')
        (self.folder / 'config').mkdir()
        (self.folder / 'config/memory_backend.json').write_text('{"backend":"v5_context"}')
        database = self.folder / 'validation_factory.db'
        with patch('memory_backend.ROOT', self.folder), patch('v5_context_memory.V5Conversation') as factory:
            memory_backend.create_memory(None, 'validation_factory', database, search='validation_search')
            factory.assert_called_once_with(None, 'validation_factory', database,
                                            'validation_search', allow_personal=False)
        self.assertFalse(database.exists())

    def test_legacy_patch_points_share_canonical_globals(self):
        targets = {'reviewed_memory_reader': ('ask', 'Reader'),
                   'episodic_memory': ('uuid',), 'persistent_memory': ('time',),
                   'episode_conversation': ('datetime',)}
        for name, attributes in targets.items():
            canonical = importlib.import_module('memoire.laboratoire.' + name)
            for attribute in attributes:
                with patch(name + '.' + attribute) as replacement:
                    self.assertIs(getattr(canonical, attribute), replacement)

    def test_store_reopen_forget_and_clock(self):
        from memoire.laboratoire.persistent_memory import Store
        database = self.folder / 'validation_store.db'
        with Store('validation_store', database) as store:
            event, _ = store.record_event(request_id='validation_event_001', role='user',
                                          channel='text', content='validation souvenir fictif')
            fact = store.remember(statement=event.content, kind='confirmed', confidence=1,
                                  event_id=event.id, evidence_quote=event.content, key='validation.fact')
            store._connection.execute('INSERT INTO feelings VALUES(?,?,?,?)',
                                      ('validation_feeling', event.id, 'triste', 150))
            with patch('persistent_memory.time.time', return_value=200):
                store.expire()
            self.assertEqual(store._connection.execute('SELECT count(*) FROM feelings').fetchone()[0], 0)
        with Store('validation_store', database) as store:
            self.assertEqual(store.rows()[0]['id'], fact.id)
            store.purge()
            self.assertEqual(store.integrity()['events'], 0)
            self.assertEqual(store.integrity()['memories'], 0)

    def test_reviewed_reader_uses_legacy_ask_patch(self):
        from memoire.laboratoire import reviewed_memory_reader as reader
        session = Mock()
        session.count_tokens = lambda _: 1
        session.ask.return_value = ('{"validation":true}', 0, {})
        self.assertEqual(reader.ask(session, 'validation_system', {}, {}), {'validation': True})
        self.assertEqual(json.loads(session.ask.call_args.args[0][1]['content']), {})

    def test_episodic_reopen_correction_conflict_and_forgetting(self):
        from memoire.laboratoire.episodic_memory import Episodes, Conflict
        from memoire.laboratoire.v5_context_memory import V5Episodes
        path = self.folder / 'validation_episodes.db'
        date = '2026-01-01T12:00:00Z'
        turns = lambda text: [{'role': 'user', 'content': text}]
        store = V5Episodes(path, 'validation_core', FictionalSearch())
        try:
            identity = store.add(date, turns('validation_old'))
            self.assertEqual(store.retrieve('validation_old')[0]['id'], identity)
            store.correct(identity, 1, date, turns('validation_new'))
            with self.assertRaises(Conflict): store.forget(identity, 1)
            self.assertEqual(store.candidates('validation_new')[0]['messages'], turns('validation_new'))
            other = Episodes(path, 'validation_core', FictionalSearch())
            try:
                self.assertEqual(other.get(identity)['revision'], 2)
                other.forget(identity, 2)
            finally: other.close()
            self.assertEqual(store.retrieve('validation_old'), [])
            self.assertEqual(store.db.execute('SELECT count(*) FROM passages').fetchone()[0], 0)
        finally: store.close()

    def test_v5_conversation_roundtrip_and_forgetting(self):
        from memoire.laboratoire.memory_backend import create_memory
        memory = create_memory(SimpleNamespace(), 'validation_conversation',
                               self.folder / 'validation_conversation.db', FictionalSearch(), 'v5_context')
        try:
            memory.ask_json = lambda *a, **k: {'feeling': 'triste'}
            answer = {'reply': 'validation_answer', 'reflection': 'ecouter', 'evidence_ids': []}
            with patch('v5_context_memory.V5Reader.answer', return_value=answer):
                self.assertEqual(memory.answer('validation_question', [], '', lambda _: True),
                                 ('validation_answer', False))
            identity = memory.current
            self.assertEqual(len(memory.episodes.get(identity)['messages']), 2)
            self.assertFalse(memory.forget(None, lambda _: False)[1])
            self.assertIsNotNone(memory.episodes.get(identity))
            self.assertTrue(memory.forget(None, lambda _: True)[1])
            self.assertIsNone(memory.episodes.get(identity))
            self.assertEqual(memory.store.integrity()['events'], 0)
            self.assertIsNone(memory.current)
        finally: memory.close()

    def test_subject_forgetting_plan_is_applied_atomically(self):
        from memoire.laboratoire.episodic_memory import Episodes, Conflict
        from memoire.laboratoire.memory_forgetting import prepare
        store = Episodes(self.folder / 'validation_forget.db', 'validation_forget', FictionalSearch())
        try:
            identity = store.add('2026-01-01T12:00:00Z', [
                {'role': 'user', 'content': 'validation_old'},
                {'role': 'assistant', 'content': 'validation_response'},
                {'role': 'user', 'content': 'validation_new'}])
            with patch('memory_forgetting.ask', side_effect=[{'subject': 'validation_old'},
                                                           {'remove': [0]}, {'remove': []}]):
                plan = prepare(SimpleNamespace(), store, 'Oublie validation_old')
            self.assertEqual(plan['plan'][0]['keep'], [2])
            store.apply_forgetting(plan['plan'], plan['version'])
            self.assertEqual(store.get(identity)['messages'], [{'role': 'user', 'content': 'validation_new'}])
            with self.assertRaises(Conflict): store.apply_forgetting(plan['plan'], plan['version'])
        finally: store.close()


if __name__ == '__main__':
    unittest.main()
