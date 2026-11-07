"""Temporary legacy import for vision.laboratoire.rendered_observation.

Keep until the laboratory navigation consumers migrate. No implementation here.
The alias preserves module identity, including private helpers and monkeypatches.
"""
from pathlib import Path
import sys

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
from vision.laboratoire import rendered_observation as _implementation

sys.modules[__name__] = _implementation
