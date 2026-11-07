"""Fake APIs only: no real focus, UI, model, or memory access."""
import ctypes
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_window_focus as native


WINDOW = {'hwnd': 0x123456789, 'pid': 42, 'created': 10.0}


class FakeAPI:
    def __init__(self, foreground=3, accepted=True):
        self.foreground = foreground
        self.accepted = accepted
        self.calls = []
        self.on_get = lambda: None
        self.on_set = lambda: None

    def GetForegroundWindow(self):
        self.on_get()
        return self.foreground

    def SetForegroundWindow(self, hwnd):
        self.calls.append(hwnd)
        if self.accepted:
            self.foreground = hwnd
        self.on_set()
        return self.accepted


class Catalog:
    def __init__(self):
        self.calls = 0
        self.on_validate = lambda: None

    def validate(self, window):
        assert window == WINDOW
        self.calls += 1
        self.on_validate()
        return True


def setup(foreground=3, accepted=True, guard=lambda: None):
    api, catalog = FakeAPI(foreground, accepted), Catalog()
    return api, catalog, native.NativeWindowFocus(catalog, guard, api)


def test_success_activates_once_and_validates_twice():
    guarded = []
    api, catalog, focus = setup(guard=lambda: guarded.append(True))
    assert focus(WINDOW, cancelled=lambda: False) is True
    assert api.calls == [WINDOW['hwnd']]
    assert catalog.calls == len(guarded) == 2


def test_already_foreground_never_activates():
    api, catalog, focus = setup(WINDOW['hwnd'])
    assert focus(WINDOW, cancelled=lambda: False) is True
    assert not api.calls
    assert catalog.calls == 2


def test_cancelled_before_validation():
    api, catalog, focus = setup()
    with pytest.raises(RuntimeError, match='native_focus_cancelled'):
        focus(WINDOW, cancelled=lambda: True)
    assert not api.calls and catalog.calls == 0


@pytest.mark.parametrize('stage', ['validate', 'guard', 'get', 'set'])
def test_cancellation_during_calls(stage):
    stopped = []
    api, catalog, focus = setup()
    cancel = lambda: stopped.append(True)
    if stage == 'validate':
        catalog.on_validate = cancel
    elif stage == 'guard':
        focus.guard = cancel
    else:
        setattr(api, 'on_' + stage, cancel)
    with pytest.raises(RuntimeError, match='native_focus_cancelled'):
        focus(WINDOW, cancelled=lambda: bool(stopped))
    assert len(api.calls) == (1 if stage == 'set' else 0)


def test_windows_denial_never_retries():
    api, _, focus = setup(accepted=False)
    with pytest.raises(RuntimeError, match='native_focus_required'):
        focus(WINDOW, cancelled=lambda: False)
    assert api.calls == [WINDOW['hwnd']]


@pytest.mark.parametrize('already', [False, True])
def test_foreground_changed_during_final_validation(already):
    api, catalog, focus = setup(WINDOW['hwnd'] if already else 3)
    def changed():
        if catalog.calls == 2:
            api.foreground = 4
    catalog.on_validate = changed
    with pytest.raises(RuntimeError, match='native_focus_required'):
        focus(WINDOW, cancelled=lambda: False)
    assert len(api.calls) == (0 if already else 1)


@pytest.mark.parametrize('when', [1, 2])
def test_identity_changed(when):
    api, catalog, focus = setup()
    def changed():
        if catalog.calls == when:
            raise RuntimeError('native_window_identity_changed')
    catalog.on_validate = changed
    with pytest.raises(RuntimeError, match='native_window_identity_changed'):
        focus(WINDOW, cancelled=lambda: False)
    assert len(api.calls) == when - 1


@pytest.mark.parametrize('when', [1, 2])
def test_guard_failure(when):
    calls = []
    def guard():
        calls.append(True)
        if len(calls) == when:
            raise RuntimeError('native_game_active')
    api, _, focus = setup(guard=guard)
    with pytest.raises(RuntimeError, match='native_game_active'):
        focus(WINDOW, cancelled=lambda: False)
    assert len(api.calls) == when - 1


def test_import_does_not_load_dll(monkeypatch):
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: pytest.fail('DLL loaded'), raising=False)
    spec = importlib.util.spec_from_file_location('validation_focus_import', native.__file__)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_loader_uses_pointer_sized_window_handles(monkeypatch):
    class Function:
        pass
    class DLL:
        GetForegroundWindow = Function()
        SetForegroundWindow = Function()
    monkeypatch.setattr(native.sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: DLL, raising=False)
    assert native._load_user32() is DLL
    assert DLL.GetForegroundWindow.argtypes == []
    assert DLL.GetForegroundWindow.restype is ctypes.c_void_p
    assert DLL.SetForegroundWindow.argtypes == [ctypes.c_void_p]
    assert DLL.SetForegroundWindow.restype is ctypes.c_int
