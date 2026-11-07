"""Bounded Win32 transport, deliberately not connected to the application.

The trusted adapter supplies preflight (identity, focus, target, geometry and
guards) before EVERY normal batch. SendInput is global: focus/user input can
still race the final check. No focus change, elevation or UIPI workaround is
attempted. GetAsyncKeyState cannot distinguish physical from injected keys and
returns zero on some access failures; preflight must establish a usable desktop.
Successful insertion is not proof that the application accepted an action.
"""
import ctypes
import sys
import threading


# Fixed-width Win32 types also make structure tests meaningful on other hosts.
DWORD, WORD, LONG = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_int32
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', LONG), ('dy', LONG), ('mouseData', DWORD),
                ('dwFlags', DWORD), ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', WORD), ('wScan', WORD), ('dwFlags', DWORD),
                ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', DWORD), ('wParamL', WORD), ('wParamH', WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', DWORD), ('data', _INPUTUNION)]


KEYUP, UNICODE, EXTENDED = 0x0002, 0x0004, 0x0001
MOVE, LEFTDOWN, LEFTUP, ABSOLUTE, VIRTUALDESK = 1, 2, 4, 0x8000, 0x4000
KEYS = {'Tab': 0x09, 'Escape': 0x1B, 'Left': 0x25, 'Up': 0x26,
        'Right': 0x27, 'Down': 0x28, 'Home': 0x24, 'End': 0x23}


def _keyboard(vk=0, scan=0, flags=0):
    return INPUT(type=1, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


def _mouse(flags, x=0, y=0):
    return INPUT(type=0, mi=MOUSEINPUT(x, y, 0, flags, 0, 0))


def _load_user32():
    if sys.platform != 'win32':
        raise OSError('native_input_requires_windows')
    dll = ctypes.WinDLL('user32', use_last_error=True)
    dll.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(INPUT), ctypes.c_int]
    dll.SendInput.restype = ctypes.c_uint32
    dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
    dll.GetAsyncKeyState.restype = ctypes.c_int16
    dll.GetSystemMetrics.argtypes = [ctypes.c_int]
    dll.GetSystemMetrics.restype = ctypes.c_int
    return dll


class NativeInputError(RuntimeError):
    """A failed insertion must never cause an automatic replay."""


class Win32Input:
    def __init__(self, user32=None):
        # No DLL is loaded at module import; tests always inject a fake API.
        self._api = _load_user32() if user32 is None else user32
        self._stopped = threading.Event()
        self._lock = threading.Lock()

    def cancel(self):
        """Permanent stop, nonblocking even while an OS call is outstanding.

        The worker completes/releases its own current batch; cancel never sends
        speculative key-ups or waits on the worker's lock.
        """
        self._stopped.set()

    def _check_stop(self, cancelled):
        if self._stopped.is_set() or cancelled():
            raise NativeInputError('native_input_stopped')

    def _send(self, entries):
        array = (INPUT * len(entries))(*entries)
        return self._api.SendInput(len(entries), array, ctypes.sizeof(INPUT))

    @staticmethod
    def _pending_releases(entries):
        pending = {}
        for entry in entries:
            if entry.type == 1:
                key = (entry.ki.wVk, entry.ki.wScan, entry.ki.dwFlags & ~KEYUP)
                if entry.ki.dwFlags & KEYUP:
                    pending.pop(key, None)
                else:
                    pending[key] = _keyboard(*key[:2], key[2] | KEYUP)
            elif entry.mi.dwFlags & LEFTDOWN:
                pending['left'] = _mouse(LEFTUP)
            elif entry.mi.dwFlags & LEFTUP:
                pending.pop('left', None)
        return list(pending.values())

    def _batch(self, entries, preflight, cancelled):
        self._check_stop(cancelled)
        # Includes modifiers, mouse buttons and VK_PACKET. Never release a key
        # merely because it is down: it may belong to the user/another process.
        if any(self._api.GetAsyncKeyState(vk) & 0x8000 for vk in range(1, 255)):
            raise NativeInputError('native_input_already_pressed')
        preflight()
        self._check_stop(cancelled)
        # Observation may take time (e.g. UIA). Refuse a user key/button that
        # appeared during preflight; the final check/send race remains.
        if any(self._api.GetAsyncKeyState(vk) & 0x8000 for vk in range(1, 255)):
            raise NativeInputError('native_input_already_pressed')
        self._check_stop(cancelled)
        try:
            count = self._send(entries)
        except Exception:
            # Unknown insertion count: no safe inference about held ownership.
            self.cancel()
            raise
        if type(count) is not int or not 0 <= count <= len(entries):
            self.cancel()
            raise NativeInputError('native_input_invalid_count')
        if count != len(entries):
            self.cancel()
            # SendInput inserts serially. Only unmatched downs in the inserted
            # prefix are ours. This release-only cleanup deliberately bypasses
            # preflight/cancellation so focus loss does not leave our key held.
            releases = self._pending_releases(entries[:count])
            if releases:
                try:
                    released = self._send(releases)
                except Exception as error:
                    raise NativeInputError('native_input_release_failed') from error
                if released != len(releases):
                    raise NativeInputError('native_input_release_failed')
            raise NativeInputError('native_input_partial')
        self._check_stop(cancelled)

    @staticmethod
    def _callbacks(preflight, cancelled):
        if not callable(preflight) or not callable(cancelled):
            raise ValueError('native_input_callbacks_required')

    def type_text(self, text, *, preflight, cancelled=lambda: False):
        self._callbacks(preflight, cancelled)
        if (type(text) is not str or not 0 < len(text) <= 4000
                or any(ord(c) < 32 and c not in '\n\t' for c in text)):
            raise ValueError('invalid_native_text')
        # Validate the entire string before any insertion (reject lone surrogates).
        text.encode('utf-16-le', errors='strict')
        with self._lock:
            for char in text:
                encoded = char.encode('utf-16-le')
                entries = []
                for i in range(0, len(encoded), 2):
                    unit = int.from_bytes(encoded[i:i + 2], 'little')
                    entries.extend((_keyboard(scan=unit, flags=UNICODE),
                                    _keyboard(scan=unit, flags=UNICODE | KEYUP)))
                self._batch(entries, preflight, cancelled)

    def key_tap(self, key, *, preflight, cancelled=lambda: False):
        self._callbacks(preflight, cancelled)
        if type(key) is not str or key not in KEYS:
            raise ValueError('native_key_not_allowed')
        vk = KEYS[key]
        flags = 0 if key in ('Tab', 'Escape') else EXTENDED
        with self._lock:
            self._batch([_keyboard(vk, flags=flags), _keyboard(vk, flags=flags | KEYUP)],
                        preflight, cancelled)

    def click(self, x, y, *, preflight, cancelled=lambda: False):
        """Click a physical-screen coordinate; caller must supply DPI-safe geometry."""
        self._callbacks(preflight, cancelled)
        if type(x) is not int or type(y) is not int:
            raise ValueError('invalid_native_coordinates')
        with self._lock:
            left, top, width, height = (self._api.GetSystemMetrics(i) for i in (76, 77, 78, 79))
            if not (0 < width <= 65536 and 0 < height <= 65536
                    and left <= x < left + width and top <= y < top + height):
                raise ValueError('native_point_outside_desktop')
            # Aim at pixel centres in the 16-bit normalized virtual desktop.
            nx = min(65535, ((x - left) * 65536 + 32768) // width)
            ny = min(65535, ((y - top) * 65536 + 32768) // height)
            self._batch([_mouse(MOVE | ABSOLUTE | VIRTUALDESK, nx, ny),
                         _mouse(LEFTDOWN), _mouse(LEFTUP)], preflight, cancelled)
