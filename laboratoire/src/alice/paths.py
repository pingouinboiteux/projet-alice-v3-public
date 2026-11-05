"""Chemins absolus derives d'une unique racine locale."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def root() -> Path:
    imposed = os.environ.get("ALICE_ROOT", "").strip()
    candidate = Path(imposed).resolve() if imposed else ROOT
    config = candidate / "config" / "alice.toml"
    if not config.is_file():
        raise RuntimeError(f"racine Alice invalide : {candidate}")
    return candidate


def inside(relative: str | Path) -> Path:
    base = root().resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"chemin hors de la racine Alice : {relative}") from exc
    return candidate


def user_data(user_id: str) -> Path:
    if not user_id or not user_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("identifiant utilisateur invalide")
    return inside(Path("data") / "users" / user_id)
