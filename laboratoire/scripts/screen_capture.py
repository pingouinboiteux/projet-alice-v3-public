"""One explicitly selected physical monitor, in memory, without input or focus."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Monitor:
    device: str
    box: tuple[int, int, int, int]
    primary: bool


def game_on_monitor(selected):
    """Conservative gate: a known game must own the foreground on this monitor."""
    import psutil
    from chat import GAMES
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetForegroundWindow.restype=w.HWND
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
    hwnd=user.GetForegroundWindow();pid=w.DWORD();rect=w.RECT()
    if not hwnd:return False
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    try:name=psutil.Process(pid.value).name().lower()
    except (psutil.Error,OSError):return False
    if name not in GAMES:return False
    with physical_coordinates(user):
        if not user.GetWindowRect(hwnd,ctypes.byref(rect)):return False
    x,y,r,b=selected.box
    return x<=(rect.left+rect.right)/2<r and y<=(rect.top+rect.bottom)/2<b


def monitors():
    user = ctypes.WinDLL('user32', use_last_error=True)
    class Info(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('rect', w.RECT), ('work', w.RECT),
                    ('flags', w.DWORD), ('device', w.WCHAR * 32)]
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)
    user.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(Info)]
    found = []
    def visit(handle, dc, rect, data):
        info = Info(); info.size = ctypes.sizeof(info)
        if user.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rect
            found.append(Monitor(info.device, (r.left, r.top, r.right, r.bottom), bool(info.flags & 1)))
        return True
    user.EnumDisplayMonitors.argtypes = [w.HDC, ctypes.c_void_p, callback_type, w.LPARAM]
    with physical_coordinates(user):
        if not user.EnumDisplayMonitors(None, None, callback_type(visit), 0):
            raise OSError('Liste des ecrans indisponible.')
    return sorted(found, key=lambda m: (not m.primary, m.device))


class physical_coordinates:
    def __init__(self, user): self.user = user
    def __enter__(self):
        self.user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        self.old = self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        if not self.old: raise OSError('Coordonnees physiques indisponibles.')
    def __exit__(self, *args):
        self.user.SetThreadDpiAwarenessContext(self.old)


def capture(selected):
    from PIL import ImageGrab, ImageDraw
    if selected not in monitors():
        raise RuntimeError('Disposition des ecrans modifiee : selectionne de nouveau ton ecran.')
    user = ctypes.WinDLL('user32', use_last_error=True)
    # Refuse a locked / secure desktop instead of remembering an older screenshot.
    user.OpenInputDesktop.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    user.OpenInputDesktop.restype = w.HANDLE
    user.GetUserObjectInformationW.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    user.CloseDesktop.argtypes = [w.HANDLE]
    desk = user.OpenInputDesktop(0, False, 0x0001)
    if not desk: raise RuntimeError('Bureau verrouille ou inaccessible.')
    try:
        name=ctypes.create_unicode_buffer(256);needed=w.DWORD()
        if not user.GetUserObjectInformationW(desk,2,name,ctypes.sizeof(name),ctypes.byref(needed)) or name.value.lower()!='default':
            raise RuntimeError('Bureau verrouille ou inaccessible.')
    finally: user.CloseDesktop(desk)
    x, y, right, bottom = selected.box
    if right-x <= 0 or bottom-y <= 0 or (right-x)*(bottom-y) > 34000000:
        raise RuntimeError('Dimensions de capture non prises en charge.')
    with physical_coordinates(user):
        image = ImageGrab.grab(bbox=selected.box, all_screens=True).convert('RGB')
        # Mask Alice's own windows: no feedback loop from its previous comments.
        draw = ImageDraw.Draw(image)
        callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        user.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        user.IsWindowVisible.argtypes = [w.HWND]
        def visit(hwnd, data):
            pid = w.DWORD(); user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid() and user.IsWindowVisible(hwnd):
                rect = w.RECT()
                if user.GetWindowRect(hwnd, ctypes.byref(rect)):
                    a,b,c,d = max(0,rect.left-x),max(0,rect.top-y),min(image.width,rect.right-x),min(image.height,rect.bottom-y)
                    if c>a and d>b: draw.rectangle((a,b,c-1,d-1), fill='black')
            return True
        user.EnumWindows.argtypes = [callback_type, w.LPARAM]
        if not user.EnumWindows(callback_type(visit), 0):
            image.close(); raise OSError('Masquage de la fenetre Alice impossible.')
    return image
