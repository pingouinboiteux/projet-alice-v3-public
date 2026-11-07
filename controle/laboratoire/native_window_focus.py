"""One ordinary foreground request for an already authorized local task.

The caller owns local imperative authorization and the anti-game guard. Windows
may refuse this request; there is no retry or restriction bypass. Foreground
verification is a point-in-time check, not a lock against subsequent user input.
"""
import ctypes
import sys


def _load_user32():
    if sys.platform != 'win32':
        raise OSError('native_windows_required')
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetForegroundWindow.argtypes = []
    api.GetForegroundWindow.restype = ctypes.c_void_p
    api.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    api.SetForegroundWindow.restype = ctypes.c_int
    return api


class NativeWindowFocus:
    def __init__(self, catalog, guard, api=None):
        self.catalog, self.guard = catalog, guard
        # Importing this module never loads a DLL or touches the desktop.
        self.api = _load_user32() if api is None else api

    @staticmethod
    def _check_cancelled(cancelled):
        if cancelled():
            raise RuntimeError('native_focus_cancelled')

    def _validate(self, window, cancelled):
        self._check_cancelled(cancelled)
        self.catalog.validate(window)
        self.guard()
        self._check_cancelled(cancelled)

    def __call__(self, window, *, cancelled):
        self._validate(window, cancelled)
        foreground = self.api.GetForegroundWindow()
        self._check_cancelled(cancelled)
        if foreground != window['hwnd']:
            if not self.api.SetForegroundWindow(window['hwnd']):
                raise RuntimeError('native_focus_required')
        self._validate(window, cancelled)
        if self.api.GetForegroundWindow() != window['hwnd']:
            raise RuntimeError('native_focus_required')
        self._check_cancelled(cancelled)
        return True
