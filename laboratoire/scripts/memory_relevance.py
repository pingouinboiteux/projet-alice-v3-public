"""Compatibility import for the private memory core owned by memoire."""
import importlib
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
_implementation = importlib.import_module('memoire.laboratoire.memory_relevance')
# Preserve module identity and patches made through the legacy name.
sys.modules[__name__] = _implementation
