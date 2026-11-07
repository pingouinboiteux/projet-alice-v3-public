"""Compatibility alias for the native backend."""
import importlib as _importlib
from pathlib import Path as _Path
import sys as _sys

_root = str(_Path(__file__).resolve().parents[2])
if _root not in _sys.path:
    _sys.path.insert(0, _root)
_impl = _importlib.import_module("controle.laboratoire.native_win32_input")
_sys.modules[__name__] = _impl
