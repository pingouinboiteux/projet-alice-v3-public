"""Compatibility checks for the desktop fixture module migration; no live desktop."""
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("first", ["vision_desktop_cases", "vision.laboratoire.vision_desktop_cases"])
def test_import_order_and_legacy_patch(first):
    code = f'''
import importlib
import sys
from unittest.mock import patch
sys.path.insert(0, {str(ROOT)!r})
sys.path.insert(0, {str(ROOT / 'laboratoire/scripts')!r})
importlib.import_module({first!r})
legacy = importlib.import_module('vision_desktop_cases')
canonical = importlib.import_module('vision.laboratoire.vision_desktop_cases')
assert legacy is canonical
original = canonical.generate_cases
with patch('vision_desktop_cases.generate_cases', return_value=['validation_stub']):
    from vision_desktop_cases import generate_cases as generator
    assert generator('validation_unused', 'desktop') == ['validation_stub']
    assert canonical.generate_cases is generator
assert canonical.generate_cases is original
'''
    subprocess.run([sys.executable, "-c", code], cwd=ROOT / "vision", check=True)


def test_invalid_split_does_not_create_data():
    sys.path.insert(0, str(ROOT))
    from vision.laboratoire.vision_desktop_cases import generate_cases

    # Reject before interpreting or creating an output path.
    with pytest.raises(ValueError, match="only desktop"):
        generate_cases(None, "heldout")
