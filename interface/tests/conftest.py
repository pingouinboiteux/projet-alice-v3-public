"""Use the same legacy imports as the laboratory entry point, without launching it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'laboratoire' / 'scripts'))
