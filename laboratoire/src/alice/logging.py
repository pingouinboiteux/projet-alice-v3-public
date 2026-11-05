"""Journal JSON ligne par ligne, lisible par un humain et par les diagnostics."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alice.paths import inside


def log_directory() -> Path:
    """Return the regular log folder or a validated local override."""
    imposed = os.environ.get("ALICE_LOG_DIRECTORY", "").strip()
    return inside(Path(imposed)) if imposed else inside("logs")


class EventLog:
    def __init__(self, organ: str, directory: Path | None = None) -> None:
        if not organ or not organ.replace("_", "").isalnum():
            raise ValueError("nom d'organe invalide")
        self.organ = organ
        self.directory = directory or log_directory()
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        return self.directory / f"{date}_{self.organ}.jsonl"

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "organ": self.organ,
            "event": event,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
        print(f"[{self.organ}] {event}", flush=True)
