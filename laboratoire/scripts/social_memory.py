"""Compatibility import for the public storage owned by memoire."""
import importlib
import sys
from pathlib import Path

# Legacy launchers put only laboratoire/scripts on sys.path.
_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
_implementation = importlib.import_module('memoire.laboratoire.social_memory')
# Share the module object, including patches through the legacy name.
sys.modules[__name__] = _implementation
