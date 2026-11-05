"""Enumeration en lecture seule des adaptateurs graphiques Windows."""

from __future__ import annotations

import ctypes
import sys
import uuid
from dataclasses import dataclass

DXGI_ERROR_NOT_FOUND = 0x887A0002
IID_IDXGI_FACTORY1 = "770aae78-f26f-4dba-a829-253c83d1b387"


class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def parse(cls, value: str) -> _Guid:
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class _Luid(ctypes.Structure):
    _fields_ = (("low", ctypes.c_uint32), ("high", ctypes.c_int32))


class _AdapterDescription(ctypes.Structure):
    _fields_ = (
        ("description", ctypes.c_wchar * 128),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("subsystem_id", ctypes.c_uint32),
        ("revision", ctypes.c_uint32),
        ("dedicated_video_memory", ctypes.c_size_t),
        ("dedicated_system_memory", ctypes.c_size_t),
        ("shared_system_memory", ctypes.c_size_t),
        ("luid", _Luid),
        ("flags", ctypes.c_uint32),
    )


@dataclass(frozen=True)
class Adapter:
    index: int
    name: str
    subsystem_id: int
    dedicated_video_memory: int
    luid_high: int
    luid_low: int
    flags: int

    @property
    def luid(self) -> tuple[int, int]:
        return self.luid_high, self.luid_low


def _method(instance: ctypes.c_void_p, slot: int, prototype):
    table = ctypes.cast(
        instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    return prototype(table[slot])


def enumerate_adapters() -> tuple[Adapter, ...]:
    if sys.platform != "win32":
        raise RuntimeError("DXGI est disponible uniquement sous Windows")
    library = ctypes.WinDLL("dxgi.dll")
    create_factory = library.CreateDXGIFactory1
    create_factory.argtypes = (ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p))
    create_factory.restype = ctypes.c_long
    factory = ctypes.c_void_p()
    result = create_factory(
        ctypes.byref(_Guid.parse(IID_IDXGI_FACTORY1)), ctypes.byref(factory)
    )
    if result < 0:
        raise OSError(result, "CreateDXGIFactory1 a echoue")

    enum_adapter = _method(
        factory,
        12,
        ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ),
    )
    release_type = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
    found: list[Adapter] = []
    try:
        index = 0
        while True:
            pointer = ctypes.c_void_p()
            result = enum_adapter(factory, index, ctypes.byref(pointer))
            if result & 0xFFFFFFFF == DXGI_ERROR_NOT_FOUND:
                break
            if result < 0:
                raise OSError(result, "EnumAdapters1 a echoue")
            try:
                description = _AdapterDescription()
                get_description = _method(
                    pointer,
                    10,
                    ctypes.WINFUNCTYPE(
                        ctypes.c_long,
                        ctypes.c_void_p,
                        ctypes.POINTER(_AdapterDescription),
                    ),
                )
                result = get_description(pointer, ctypes.byref(description))
                if result < 0:
                    raise OSError(result, "GetDesc1 a echoue")
                found.append(
                    Adapter(
                        index=index,
                        name=description.description,
                        subsystem_id=description.subsystem_id,
                        dedicated_video_memory=description.dedicated_video_memory,
                        luid_high=description.luid.high,
                        luid_low=description.luid.low,
                        flags=description.flags,
                    )
                )
            finally:
                _method(pointer, 2, release_type)(pointer)
            index += 1
    finally:
        _method(factory, 2, release_type)(factory)
    return tuple(found)
