"""Laboratory memory core; data and external contracts stay in laboratoire."""
import sys
from pathlib import Path

# External contracts still use the legacy scripts import namespace.
_scripts = str(Path(__file__).resolve().parents[2] / 'laboratoire' / 'scripts')
if _scripts not in sys.path:
    sys.path.append(_scripts)
