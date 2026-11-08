"""Both import paths must share one module, including monkeypatched globals."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('name', ['desktop_style', 'desktop_services', 'desktop_confirmation', 'desktop_observation', 'desktop_commands', 'desktop_delivery'])
@pytest.mark.parametrize('canonical_first', [False, True])
def test_alias_identity_and_inert_import_from_unrelated_directory(tmp_path, name, canonical_first):
    root = Path(__file__).resolve().parents[2]
    code = '''
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

root, name, canonical_first = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == 'True'
sys.path.insert(0, str(root / 'laboratoire' / 'scripts'))
if canonical_first:
    sys.path.insert(0, str(root))
canonical = 'interface.laboratoire.' + name
paths = (canonical, name) if canonical_first else (name, canonical)
with patch('tkinter.Tk', side_effect=AssertionError('unexpected Tk')), \
     patch('tkinter.Toplevel', side_effect=AssertionError('unexpected window')):
    first, second = (importlib.import_module(path) for path in paths)
assert first is second
assert Path(first.__file__).resolve().parent == root / 'interface' / 'laboratoire'
first.validation_alias_marker = object()
assert second.validation_alias_marker is first.validation_alias_marker
assert not any(name in sys.modules for name in
               ('alice_desktop', 'chat', 'voice_link', 'hearing_link', 'memory_backend'))
'''
    subprocess.run([sys.executable, '-I', '-B', '-c', code, str(root), name,
                    str(canonical_first)], cwd=tmp_path, check=True,
                   capture_output=True, text=True, timeout=20)
