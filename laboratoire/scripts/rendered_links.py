"""Temporary legacy alias; implementation lives in vision.laboratoire.rendered_links.

Preserves module identity and monkeypatches until link consumers migrate.
"""
from pathlib import Path
import sys

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
from vision.laboratoire import rendered_links as _implementation

sys.modules[__name__] = _implementation
