"""Resolve private worker outputs consistently, including compatibility junctions."""
from pathlib import Path


def private_output_path(root: Path, relative: str) -> Path:
    base = root.resolve()
    allowed = (base / 'logs').resolve()
    output = (base / relative).resolve()
    if not allowed.is_relative_to(base) or not output.is_relative_to(allowed) or not output.is_dir():
        raise ValueError('Invalid private output directory')
    return output
