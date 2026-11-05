"""Identification materielle sans index suppose."""

from alice.hardware.gpu import (
    ALICE_GPU_SUBSYSTEM_ID,
    BODY_GPU_SUBSYSTEM_ID,
    alice_pci_bus,
    alice_vulkan_index,
    body_adapter,
)

__all__ = [
    "ALICE_GPU_SUBSYSTEM_ID",
    "BODY_GPU_SUBSYSTEM_ID",
    "alice_pci_bus",
    "alice_vulkan_index",
    "body_adapter",
]
