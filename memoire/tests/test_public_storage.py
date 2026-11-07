"""Storage contract: standard library only, isolated fictional data."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'laboratoire/scripts'))
import social_memory
from memoire.laboratoire import social_memory as canonical


class PublicStorageTests(unittest.TestCase):
    def setUp(self):
        validation = ROOT / 'data/validation'
        validation.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix='validation_public_', dir=validation)
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'validation_public.db'
        self.now = 1800000000

    def open(self):
        memory = social_memory.PublicMemory(self.path, 'validation_public', clock=lambda: self.now)
        self.addCleanup(memory.close)
        return memory

    def test_import_identity_and_patch(self):
        self.assertIs(social_memory, canonical)
        with patch('social_memory.datetime') as clock:
            self.open().today()
            clock.fromtimestamp.assert_called_once_with(self.now)

    def test_import_orders_from_unrelated_directory(self):
        for order in ('import social_memory; from memoire.laboratoire import social_memory as other',
                      'from memoire.laboratoire import social_memory as other; import social_memory'):
            env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT/'laboratoire/scripts'), str(ROOT))), PYTHONDONTWRITEBYTECODE='1')
            subprocess.run([sys.executable, '-B', '-c', order+'; assert social_memory is other'], cwd=self.folder.name, env=env, check=True)
        env['PYTHONPATH'] = str(ROOT/'laboratoire/scripts')
        subprocess.run([sys.executable, '-B', '-c', 'import social_memory; assert social_memory.PublicMemory'], cwd=self.folder.name, env=env, check=True)

    def test_identity_guards_before_file_creation(self):
        for identity, filename, allow in [('validation_public', 'public_channels.db', False),
                                           ('public_channels', 'public_channels.db', False),
                                           ('validation_public', 'validation_other.db', True),
                                           ('invalid', 'invalid.db', True)]:
            with self.assertRaises(ValueError):
                social_memory.PublicMemory(Path(self.folder.name)/filename, identity, allow_public=allow)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])
        # Check authorization without opening any production-named database.
        with patch('social_memory.sqlite3.connect', side_effect=RuntimeError('validation_probe')):
            with self.assertRaisesRegex(RuntimeError, 'validation_probe'):
                social_memory.PublicMemory(Path(self.folder.name)/'public_channels.db', 'public_channels', allow_public=True)

    def test_restart_delivery_platform_and_forget(self):
        memory = self.open()
        memory.record('twitch', 'validation_author', 'validation_question', 'validation_reply')
        self.assertFalse(memory.context('twitch', 'validation_author')[1])
        memory.delivered('twitch', 'validation_author')
        memory.close()
        memory = self.open()
        self.assertTrue(memory.context('twitch', 'validation_author')[1])
        self.assertEqual(memory.context('discord', 'validation_author'), ([], False))
        self.assertEqual(memory.context('twitch', 'validation_other'), ([], False))
        memory.record('twitch', 'validation_author', 'validation_next', 'validation_answer')
        self.assertTrue(memory.context('twitch', 'validation_author')[1])
        self.now += 86400
        self.assertFalse(memory.context('twitch', 'validation_author')[1])
        memory.forget('twitch', 'validation_author')
        self.assertEqual(memory.context('twitch', 'validation_author'), ([], False))
        memory.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            memory.context('twitch', 'validation_author')

    def test_invalid_platform_and_author(self):
        memory = self.open()
        for source, author in [('invalid', 'validation_author'), ('twitch', ''), ('discord', 1), ('twitch', 'x'*81)]:
            with self.assertRaises(ValueError):
                memory.record(source, author, 'validation_text', 'validation_reply')
        self.assertEqual(memory.db.execute('SELECT count(*) FROM public').fetchone()[0], 0)

    def test_pair_limits_truncation_and_expiry(self):
        memory = self.open()
        for index in range(40):
            memory.record('discord', 'validation_author', str(index), 'validation_reply')
        turns, _ = memory.context('discord', 'validation_author')
        self.assertEqual(len(turns), 24)
        self.assertEqual(turns[-2]['content'], '39')
        for index in range(10):
            memory.record('discord', 'validation_long', 'x'*2500, 'y'*700)
        turns, _ = memory.context('discord', 'validation_long')
        self.assertEqual([len(t['content']) for t in turns], [2000, 600, 2000, 600])
        self.now += 180*86400
        self.assertTrue(memory.context('discord', 'validation_author')[0])
        self.now += 1
        self.assertEqual(memory.context('discord', 'validation_author'), ([], False))

    def test_author_cap_and_secure_delete(self):
        memory = self.open()
        self.assertEqual(memory.db.execute('PRAGMA secure_delete').fetchone()[0], 1)
        with memory.db:
            memory.db.executemany('INSERT INTO public VALUES(?,?,?,?,?)',
                [('twitch', 'validation_'+str(i), self.now, '', '[]') for i in range(1002)])
        memory.prune()
        authors = {r[0] for r in memory.db.execute('SELECT author FROM public')}
        self.assertEqual(len(authors), 1000)
        self.assertNotIn('validation_0', authors)
        self.assertNotIn('validation_1', authors)
        self.assertIn('validation_1001', authors)


if __name__ == '__main__':
    unittest.main()
