"""Runtime FPS protection; retained implementation, no training driver."""
import ctypes
import threading
import time
from ctypes import wintypes

class GameFocus:
    def __init__(self, pid):
        self.pid = pid
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.ready = threading.Event()
        self.foreground = False
        self.since = None
        self.transitions = 0
        self.error = None
        self.thread = threading.Thread(target=self.monitor, daemon=True)

    def start(self):
        self.thread.start()
        assert self.ready.wait(5), "Foreground instrument did not start"

    def monitor(self):
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.DWORD),
            ]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            while not self.done.is_set():
                handle = user32.GetForegroundWindow()
                process = wintypes.DWORD()
                if handle:
                    assert user32.GetWindowThreadProcessId(
                        handle, ctypes.byref(process)
                    ), "Cannot resolve foreground process"
                active = bool(handle) and process.value == self.pid
                with self.lock:
                    if active != self.foreground:
                        self.transitions += 1
                        self.foreground = active
                        self.since = time.monotonic() if active else None
                self.ready.set()
                self.done.wait(0.05)
        except Exception as exc:  # noqa: BLE001 - instrument failures must stop work
            with self.lock:
                self.error = repr(exc)
            self.ready.set()

    def state(self):
        with self.lock:
            assert self.error is None, self.error
            return {
                "foreground": self.foreground,
                "foreground_seconds": time.monotonic() - self.since
                if self.since is not None
                else 0.0,
                "transitions": self.transitions,
            }

    def close(self):
        self.done.set()
        self.thread.join(5)
        assert not self.thread.is_alive()
