"""Original personality, copied locally; permissions belong to each channel."""
from pathlib import Path

PERSONALITY = (Path(__file__).resolve().parents[1] / 'personality/alice.md').read_text(encoding='utf-8')
