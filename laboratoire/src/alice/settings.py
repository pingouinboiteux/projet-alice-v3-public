"""Lecture typee de la configuration partagee."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from alice.paths import inside


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name)
        if not isinstance(value, dict):
            raise KeyError(f"section de configuration absente : {name}")
        return value

    def value(self, section: str, key: str, expected: type):
        value = self.section(section).get(key)
        if expected is int and isinstance(value, bool):
            raise TypeError(f"{section}.{key} doit etre un entier")
        if not isinstance(value, expected):
            raise TypeError(f"{section}.{key} doit etre {expected.__name__}")
        return value

    def path(self, key: str) -> Path:
        return inside(self.value("models", key, str))


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    path = inside(Path("config") / "alice.toml")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    return Settings(data)
