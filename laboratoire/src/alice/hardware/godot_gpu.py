"""Selection verifiee du GPU du corps dans l'inventaire propre a Godot."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from alice.hardware.gpu import body_adapter

_DEVICE_LINE = re.compile(
    r"^\s*#(?P<index>\d+):\s+(?P<name>.+?)\s+-\s+Supported,\s+"
    r"(?P<kind>Integrated|Discrete|CPU)\s*$",
    re.MULTILINE,
)
_SELECTED_LINE = re.compile(
    r"Using Device #(?P<index>\d+):\s*(?P<name>.+?)\s*$", re.MULTILINE
)


@dataclass(frozen=True)
class GodotDevice:
    index: int
    name: str
    kind: str


def parse_devices(text: str) -> tuple[GodotDevice, ...]:
    return tuple(
        GodotDevice(
            index=int(match.group("index")),
            name=match.group("name").strip(),
            kind=match.group("kind"),
        )
        for match in _DEVICE_LINE.finditer(text)
    )


def select_body_device(
    devices: tuple[GodotDevice, ...], expected_name: str
) -> GodotDevice:
    expected = expected_name.casefold()
    matches = [device for device in devices if expected in device.name.casefold()]
    if len(matches) != 1:
        raise RuntimeError(
            "le GPU du corps attendu n'est pas unique dans l'inventaire Godot"
        )
    return matches[0]


def probe_body_device(
    godot: Path, project: Path, appdata: Path, log_path: Path
) -> GodotDevice:
    adapter = body_adapter()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["APPDATA"] = str(appdata)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [
            str(godot),
            "--path",
            str(project),
            "--editor",
            "--rendering-method",
            "mobile",
            "--rendering-driver",
            "d3d12",
            "--quit-after",
            "1",
            "--audio-driver",
            "Dummy",
            "--verbose",
            "--log-file",
            str(log_path),
        ],
        cwd=str(project),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"la sonde Godot s'est arretee avec le code {result.returncode}"
        )
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError("le journal de la sonde GPU est illisible") from exc
    devices = parse_devices(output)
    if not devices:
        raise RuntimeError("Godot n'a fourni aucun inventaire GPU")
    return select_body_device(devices, adapter.name)


def render_command(
    godot: Path, project: Path, device: GodotDevice, log_path: Path
) -> tuple[str, ...]:
    return (
        str(godot),
        "--path",
        str(project),
        "--rendering-method",
        "mobile",
        "--rendering-driver",
        "d3d12",
        "--gpu-index",
        str(device.index),
        "--log-file",
        str(log_path),
    )


def wait_for_selected_device(
    log_path: Path, expected_name: str, timeout: float = 15.0
) -> str:
    deadline = time.monotonic() + timeout
    expected = expected_name.casefold()
    while time.monotonic() < deadline:
        try:
            output = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            time.sleep(0.1)
            continue
        match = _SELECTED_LINE.search(output)
        if match is None:
            time.sleep(0.1)
            continue
        selected = match.group("name").strip()
        if expected not in selected.casefold():
            raise RuntimeError(f"Godot a selectionne la mauvaise carte : {selected}")
        return selected
    raise RuntimeError("Godot n'a pas confirme la carte utilisee pour le corps")
