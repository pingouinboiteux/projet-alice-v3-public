"""Isolated OBS file contracts; no OBS, voice or application startup."""
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'laboratoire' / 'scripts'))
from integrations.laboratoire import obs_subtitles


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        validation = ROOT / 'data' / 'validation'
        validation.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix='validation_obs_', dir=validation)
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'validation_subtitles.txt'

    def test_import_identity_in_both_orders(self):
        for first, second in (
            ('obs_subtitles', 'integrations.laboratoire.obs_subtitles'),
            ('integrations.laboratoire.obs_subtitles', 'obs_subtitles'),
        ):
            code = (
                'import importlib, sys; '
                f'sys.path[:0] = {[str(ROOT), str(ROOT / "laboratoire" / "scripts")]!r}; '
                f'a = importlib.import_module({first!r}); '
                f'b = importlib.import_module({second!r}); '
                'assert a is b; assert a.Subtitles is b.Subtitles'
            )
            subprocess.run([sys.executable, '-B', '-c', code], check=True)

    def test_constructor_clears_existing_file(self):
        self.path.write_text('validation_old', encoding='utf-8')
        subtitles = obs_subtitles.Subtitles(self.path)
        self.assertEqual(subtitles.path, self.path)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '')
        self.assertEqual(subtitles.generation, 1)

    def test_normalization_limit_and_generation(self):
        subtitles = obs_subtitles.Subtitles(self.path)
        self.assertEqual(subtitles.show('  validation_été\n\t texte  '), 2)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'validation_été texte')
        self.assertEqual(subtitles.show('x' * 4001), 3)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'x' * 4000)

    def test_stale_ticket_preserves_new_text(self):
        subtitles = obs_subtitles.Subtitles(self.path)
        first = subtitles.show('validation_first')
        second = subtitles.show('validation_second')
        subtitles.clear(first)
        self.assertEqual(subtitles.generation, second)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'validation_second')
        subtitles.clear(second)
        self.assertEqual(subtitles.generation, second + 1)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '')

    def test_atomic_replace_and_parent_creation(self):
        self.path = self.path.parent / 'validation_nested' / self.path.name
        subtitles = obs_subtitles.Subtitles(self.path)
        replace = obs_subtitles.os.replace
        def inspect(source, destination):
            self.assertEqual(source, self.path.with_suffix('.tmp'))
            self.assertEqual(destination, self.path)
            self.assertEqual(destination.read_text(encoding='utf-8'), '')
            self.assertEqual(source.read_text(encoding='utf-8'), 'validation_new')
            replace(source, destination)
        with patch.object(obs_subtitles.os, 'replace', side_effect=inspect):
            subtitles.show('validation_new')
        self.assertFalse(self.path.with_suffix('.tmp').exists())

    def test_error_callback_cleanup_and_legacy_patch(self):
        importlib.import_module('obs_subtitles')
        error = Mock()
        subtitles = obs_subtitles.Subtitles(self.path, error)
        subtitles.show('validation_preserved')
        with patch('obs_subtitles.os.replace', side_effect=PermissionError('validation_locked')):
            subtitles.show('validation_failed')
            subtitles.clear()
        self.assertEqual(error.call_count, 2)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'validation_preserved')
        self.assertFalse(self.path.with_suffix('.tmp').exists())


if __name__ == '__main__':
    unittest.main()
