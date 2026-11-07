"""Temporary legacy alias; implementation lives in vision.laboratoire.vision_bench_cases.

Preserves module identity and monkeypatches until bench consumers migrate.
"""
from pathlib import Path
import sys

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
from vision.laboratoire import vision_bench_cases as _implementation

sys.modules[__name__] = _implementation
