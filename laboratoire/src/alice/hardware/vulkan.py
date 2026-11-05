"""Enumeration Vulkan avec l'identifiant Windows de chaque carte."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

VK_SUCCESS = 0
API_VERSION_1_1 = (1 << 22) | (1 << 12)
TYPE_APPLICATION_INFO = 0
TYPE_INSTANCE_CREATE_INFO = 1
TYPE_PHYSICAL_DEVICE_PROPERTIES_2 = 1000059001
TYPE_PHYSICAL_DEVICE_ID_PROPERTIES = 1000071004


class _ApplicationInfo(ctypes.Structure):
    _fields_ = (
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("pApplicationName", ctypes.c_char_p),
        ("applicationVersion", ctypes.c_uint32),
        ("pEngineName", ctypes.c_char_p),
        ("engineVersion", ctypes.c_uint32),
        ("apiVersion", ctypes.c_uint32),
    )


class _InstanceCreateInfo(ctypes.Structure):
    _fields_ = (
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.POINTER(_ApplicationInfo)),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    )


class _IdProperties(ctypes.Structure):
    _fields_ = (
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("deviceUUID", ctypes.c_uint8 * 16),
        ("driverUUID", ctypes.c_uint8 * 16),
        ("deviceLUID", ctypes.c_uint8 * 8),
        ("deviceNodeMask", ctypes.c_uint32),
        ("deviceLUIDValid", ctypes.c_uint32),
    )


class _Properties2(ctypes.Structure):
    _fields_ = (
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("blob", ctypes.c_uint8 * 2048),
    )


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    luid_high: int
    luid_low: int
    luid_valid: bool

    @property
    def luid(self) -> tuple[int, int]:
        return self.luid_high, self.luid_low


def enumerate_devices() -> tuple[Device, ...]:
    try:
        loader = ctypes.WinDLL("vulkan-1.dll")
    except OSError as exc:
        raise RuntimeError(f"chargeur Vulkan introuvable : {exc}") from exc

    loader.vkCreateInstance.argtypes = (
        ctypes.POINTER(_InstanceCreateInfo),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    loader.vkCreateInstance.restype = ctypes.c_int32
    loader.vkEnumeratePhysicalDevices.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
    )
    loader.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
    loader.vkGetPhysicalDeviceProperties2.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_Properties2),
    )
    loader.vkGetPhysicalDeviceProperties2.restype = None
    loader.vkDestroyInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    loader.vkDestroyInstance.restype = None

    application = _ApplicationInfo(
        sType=TYPE_APPLICATION_INFO,
        pNext=None,
        pApplicationName=b"alice-hardware",
        applicationVersion=1,
        pEngineName=b"alice",
        engineVersion=1,
        apiVersion=API_VERSION_1_1,
    )
    creation = _InstanceCreateInfo(
        sType=TYPE_INSTANCE_CREATE_INFO,
        pNext=None,
        flags=0,
        pApplicationInfo=ctypes.pointer(application),
        enabledLayerCount=0,
        ppEnabledLayerNames=None,
        enabledExtensionCount=0,
        ppEnabledExtensionNames=None,
    )
    instance = ctypes.c_void_p()
    code = loader.vkCreateInstance(ctypes.byref(creation), None, ctypes.byref(instance))
    if code != VK_SUCCESS:
        raise RuntimeError(f"vkCreateInstance a refuse avec le code {code}")

    try:
        count = ctypes.c_uint32(0)
        code = loader.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None)
        if code != VK_SUCCESS:
            raise RuntimeError(f"enumeration Vulkan refusee avec le code {code}")
        pointers = (ctypes.c_void_p * count.value)()
        code = loader.vkEnumeratePhysicalDevices(
            instance, ctypes.byref(count), pointers
        )
        if code != VK_SUCCESS:
            raise RuntimeError(f"lecture Vulkan refusee avec le code {code}")
        found: list[Device] = []
        for index in range(count.value):
            identity = _IdProperties(
                sType=TYPE_PHYSICAL_DEVICE_ID_PROPERTIES, pNext=None
            )
            properties = _Properties2(
                sType=TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
                pNext=ctypes.cast(ctypes.byref(identity), ctypes.c_void_p),
            )
            loader.vkGetPhysicalDeviceProperties2(
                ctypes.c_void_p(pointers[index]), ctypes.byref(properties)
            )
            raw_name = bytes(properties.blob[20:276]).split(b"\0", 1)[0]
            luid = bytes(identity.deviceLUID)
            found.append(
                Device(
                    index=index,
                    name=raw_name.decode("utf-8", errors="replace") or f"carte {index}",
                    luid_low=int.from_bytes(luid[:4], "little"),
                    luid_high=int.from_bytes(luid[4:], "little", signed=True),
                    luid_valid=bool(identity.deviceLUIDValid),
                )
            )
        return tuple(found)
    finally:
        loader.vkDestroyInstance(instance, None)
