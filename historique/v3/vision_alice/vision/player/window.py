"""Identite de la fenetre active, lue directement a Windows."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from collections.abc import Callable
from typing import Protocol


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass(frozen=True)
class ForegroundWindow:
    handle: int
    process_id: int
    executable: str
    title: str
    bounds: tuple[int, int, int, int] | None = None


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class ForegroundProbe(Protocol):
    def read(self) -> ForegroundWindow | None: ...


class GameWindowProbe(Protocol):
    def find_matching(
        self, matches_executable: Callable[[str], bool],
    ) -> ForegroundWindow | None: ...


def _read_window(handle: int) -> ForegroundWindow | None:
    """Lit une fenetre Windows sans lui envoyer de message."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    get_client_rect = getattr(user32, "GetClientRect", None)
    client_to_screen = getattr(user32, "ClientToScreen", None)
    if get_client_rect is not None:
        get_client_rect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        get_client_rect.restype = wintypes.BOOL
    if client_to_screen is not None:
        client_to_screen.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
        client_to_screen.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    if not process_id.value:
        return None
    process = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value,
    )
    if not process:
        return None
    try:
        size = wintypes.DWORD(32_768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            process, 0, path, ctypes.byref(size),
        ):
            return None
    finally:
        kernel32.CloseHandle(process)
    length = user32.GetWindowTextLengthW(handle)
    title = ctypes.create_unicode_buffer(max(1, length + 1))
    user32.GetWindowTextW(handle, title, len(title))
    bounds = None
    client = _RECT()
    if get_client_rect is not None and client_to_screen is not None and get_client_rect(
        handle, ctypes.byref(client),
    ):
        top_left = _POINT(client.left, client.top)
        bottom_right = _POINT(client.right, client.bottom)
        if client_to_screen(handle, ctypes.byref(top_left)) and client_to_screen(
            handle, ctypes.byref(bottom_right),
        ):
            if bottom_right.x > top_left.x and bottom_right.y > top_left.y:
                bounds = (
                    int(top_left.x),
                    int(top_left.y),
                    int(bottom_right.x),
                    int(bottom_right.y),
                )
    return ForegroundWindow(
        int(handle),
        int(process_id.value),
        path.value,
        title.value,
        bounds,
    )


class WindowsForegroundProbe:
    """Lit le focus sans envoyer de message a la fenetre."""

    def read(self) -> ForegroundWindow | None:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        raw_handle = user32.GetForegroundWindow()
        if raw_handle in (None, 0):
            return None
        handle = int(raw_handle)
        if not handle:
            return None
        return _read_window(handle)


class WindowsGameWindowProbe:
    """Trouve une fenetre de jeu visible, meme lors d'une perte de focus breve."""

    def find_matching(
        self, matches_executable: Callable[[str], bool],
    ) -> ForegroundWindow | None:
        if not callable(matches_executable):
            raise TypeError("le filtre executable doit etre appelable")
        user32 = ctypes.windll.user32
        enum_windows = getattr(user32, "EnumWindows", None)
        is_visible = getattr(user32, "IsWindowVisible", None)
        is_iconic = getattr(user32, "IsIconic", None)
        if enum_windows is None or is_visible is None or is_iconic is None:
            return None
        found: ForegroundWindow | None = None
        callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
        )

        @callback_type
        def visit(raw_handle, _lparam):
            nonlocal found
            handle = int(raw_handle)
            if not handle or not is_visible(handle) or is_iconic(handle):
                return True
            candidate = _read_window(handle)
            if candidate is None or not matches_executable(candidate.executable):
                return True
            found = candidate
            return False

        enum_windows(visit, 0)
        return found
