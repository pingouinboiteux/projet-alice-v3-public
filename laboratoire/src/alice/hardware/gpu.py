"""Selection de la carte reservee a Alice par identite physique."""

from __future__ import annotations

import os
import re
import subprocess

from alice.hardware.dxgi import Adapter, enumerate_adapters
from alice.hardware.vulkan import enumerate_devices
from alice.settings import load_settings

ALICE_GPU_SUBSYSTEM_ID = 0x240E1458
BODY_GPU_SUBSYSTEM_ID = 0x364E1849


def _configured_subsystem_id(key: str, expected: int) -> int:
    raw = load_settings().value("hardware", key, str)
    try:
        value = int(raw, 16)
    except ValueError as exc:
        raise ValueError("identite de carte invalide dans la configuration") from exc
    if value != expected:
        raise RuntimeError("l'identite de carte ne correspond pas au contrat materiel")
    return value


def _target_subsystem_id() -> int:
    return _configured_subsystem_id("alice_gpu_subsystem_id", ALICE_GPU_SUBSYSTEM_ID)


def body_adapter() -> Adapter:
    target = _configured_subsystem_id("body_gpu_subsystem_id", BODY_GPU_SUBSYSTEM_ID)
    matches = [
        item
        for item in enumerate_adapters()
        if item.subsystem_id == target and not item.flags
    ]
    if len(matches) != 1:
        raise RuntimeError("la carte integree du corps n'est pas unique dans DXGI")
    return matches[0]


def alice_vulkan_index() -> int:
    target = _target_subsystem_id()
    adapters = [
        item
        for item in enumerate_adapters()
        if item.subsystem_id == target and not item.flags
    ]
    if len(adapters) != 1:
        raise RuntimeError("la carte reservee n'est pas unique dans DXGI")
    matches = [
        item
        for item in enumerate_devices()
        if item.luid_valid and item.luid == adapters[0].luid
    ]
    if len(matches) != 1:
        raise RuntimeError("la carte reservee n'est pas unique dans Vulkan")
    return matches[0].index


def _parse_bus_inventory(text: str, subsystem_id: int) -> int:
    marker = f"SUBSYS_{subsystem_id:08X}"
    blocks = re.split(r"\r?\n\s*\r?\n", text)
    candidates: list[int] = []
    for block in blocks:
        if marker not in block.upper():
            continue
        match = re.search(r"BUS\s*=\s*(\d+)", block, flags=re.IGNORECASE)
        if match:
            candidates.append(int(match.group(1)))
    if len(candidates) != 1:
        raise RuntimeError("le bus PCI de la carte reservee n'est pas unique")
    return candidates[0]


def alice_pci_bus() -> int:
    override = os.environ.get("ALICE_GPU_PCI_BUS", "").strip()
    if override:
        return int(override)
    script = (
        "$items=Get-PnpDevice -Class Display -PresentOnly;"
        "foreach($d in $items){"
        "$b=(Get-PnpDeviceProperty -InstanceId $d.InstanceId "
        "-KeyName 'DEVPKEY_Device_BusNumber' -ErrorAction Stop).Data;"
        "Write-Output ('ID='+$d.InstanceId);Write-Output ('BUS='+$b);Write-Output ''}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        errors="replace",
    )
    return _parse_bus_inventory(result.stdout, _target_subsystem_id())
