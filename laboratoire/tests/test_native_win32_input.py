"""No real Windows API, UI, input or memory access in these tests."""
import ctypes
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_win32_input as native


class FakeUser32:
    def __init__(self, counts=()):
        self.calls = []
        self.counts = iter(counts)
        self.pressed = set()
        self.metrics = {76: -1920, 77: -100, 78: 3840, 79: 1180}
        self.order = []

    def GetAsyncKeyState(self, vk):
        return 0x8000 if vk in self.pressed else 0

    def GetSystemMetrics(self, metric):
        return self.metrics[metric]

    def SendInput(self, count, array, size):
        assert size == ctypes.sizeof(native.INPUT)
        self.order.append('send')
        self.calls.append([native.INPUT.from_buffer_copy(array[i]) for i in range(count)])
        return next(self.counts, count)


def setup(counts=()):
    api = FakeUser32(counts)
    transport = native.Win32Input(api)
    return api, transport


def test_windows_structure_layout():
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(native.INPUT) == 40
        assert native.INPUT.data.offset == 8
        assert ctypes.sizeof(native.KEYBDINPUT) == 24
        assert native.KEYBDINPUT.dwExtraInfo.offset == 16
        assert ctypes.sizeof(native.MOUSEINPUT) == 32
        assert native.MOUSEINPUT.dwExtraInfo.offset == 24
    else:
        assert ctypes.sizeof(native.INPUT) == 28
        assert native.INPUT.data.offset == 4


def test_import_does_not_load_library(monkeypatch):
    import importlib.util
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: pytest.fail('DLL loaded'), raising=False)
    spec = importlib.util.spec_from_file_location('validation_transport_import', native.__file__)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_unicode_batches_and_surrogate_pair():
    api, transport = setup()
    transport.type_text('Aé😀', preflight=lambda: api.order.append('preflight'))
    assert api.order == ['preflight', 'send'] * 3
    assert [len(c) for c in api.calls] == [2, 2, 4]
    assert [e.ki.wScan for c in api.calls for e in c][::2] == [65, 233, 0xD83D, 0xDE00]
    for call in api.calls:
        assert all(e.type == 1 and e.ki.wVk == 0 for e in call)
        assert [e.ki.dwFlags for e in call] == [4, 6] * (len(call) // 2)


@pytest.mark.parametrize('text', ['', 'a' * 4001, '\x00', '\r', 42, 'ok\ud800'])
def test_invalid_text_never_inserts(text):
    api, transport = setup()
    with pytest.raises((ValueError, UnicodeEncodeError)):
        transport.type_text(text, preflight=lambda: None)
    assert not api.calls


@pytest.mark.parametrize('key', list(native.KEYS))
def test_key_allowlist(key):
    api, transport = setup()
    transport.key_tap(key, preflight=lambda: None)
    down, up = api.calls[0]
    assert down.ki.wVk == up.ki.wVk == native.KEYS[key]
    assert up.ki.dwFlags == down.ki.dwFlags | native.KEYUP
    assert bool(down.ki.dwFlags & native.EXTENDED) == (key not in ('Tab', 'Escape'))


@pytest.mark.parametrize('key', ['Enter', 'Ctrl', 'Alt+F4', None, ['Tab']])
def test_unknown_keys_rejected(key):
    api, transport = setup()
    with pytest.raises(ValueError):
        transport.key_tap(key, preflight=lambda: None)
    assert not api.calls


@pytest.mark.parametrize('vk', [1, 2, 4, 5, 6, 16, 17, 18, 65, 91, 160, 231])
def test_pressed_buttons_keys_modifiers_are_not_released(vk):
    api, transport = setup()
    api.pressed.add(vk)
    with pytest.raises(native.NativeInputError, match='already_pressed'):
        transport.key_tap('Tab', preflight=lambda: None)
    transport.cancel()
    assert not api.calls


def test_stale_low_key_state_bit_does_not_block():
    api, transport = setup()
    api.GetAsyncKeyState = lambda vk: 1
    transport.key_tap('Tab', preflight=lambda: None)
    assert len(api.calls) == 1


@pytest.mark.parametrize('vk', [1, 17, 65])
def test_user_press_during_preflight_blocks_insertion(vk):
    api, transport = setup()
    with pytest.raises(native.NativeInputError, match='already_pressed'):
        transport.key_tap('Tab', preflight=lambda: api.pressed.add(vk))
    assert not api.calls


def test_preflight_failure_and_cancel_during_preflight():
    api, transport = setup()
    def fail():
        raise ValueError('focus_lost')
    with pytest.raises(ValueError, match='focus_lost'):
        transport.click(20, 30, preflight=fail)
    with pytest.raises(native.NativeInputError, match='stopped'):
        transport.key_tap('Tab', preflight=transport.cancel)
    assert not api.calls


def test_preflight_each_character_and_stop_before_next_batch():
    api, transport = setup()
    def check():
        if api.calls:
            raise ValueError('target_changed')
    with pytest.raises(ValueError, match='target_changed'):
        transport.type_text('abc', preflight=check)
    assert len(api.calls) == 1


def test_external_cancelled_callback():
    api, transport = setup()
    with pytest.raises(native.NativeInputError, match='stopped'):
        transport.type_text('abc', preflight=lambda: None, cancelled=lambda: bool(api.calls))
    assert len(api.calls) == 1


@pytest.mark.parametrize('count,cleanup', [(0, False), (1, True)])
def test_partial_key_releases_only_inserted_down(count, cleanup):
    api, transport = setup([count])
    with pytest.raises(native.NativeInputError, match='partial'):
        transport.key_tap('Home', preflight=lambda: None)
    assert len(api.calls) == 1 + cleanup
    if cleanup:
        assert len(api.calls[1]) == 1
        assert api.calls[1][0].ki.wVk == 0x24
        assert api.calls[1][0].ki.dwFlags == native.KEYUP | native.EXTENDED
    with pytest.raises(native.NativeInputError, match='stopped'):
        transport.key_tap('Tab', preflight=lambda: None)


@pytest.mark.parametrize('count,scan', [(0, None), (1, 0xD83D), (2, None), (3, 0xDE00)])
def test_partial_unicode_releases_only_unmatched_unit(count, scan):
    api, transport = setup([count])
    with pytest.raises(native.NativeInputError, match='partial'):
        transport.type_text('😀', preflight=lambda: None)
    assert len(api.calls) == 1 + (scan is not None)
    if scan is not None:
        assert len(api.calls[1]) == 1
        assert api.calls[1][0].ki.wScan == scan
        assert api.calls[1][0].ki.dwFlags == native.UNICODE | native.KEYUP


@pytest.mark.parametrize('count', [0, 1, 2])
def test_partial_click_releases_only_inserted_button(count):
    api, transport = setup([count])
    with pytest.raises(native.NativeInputError, match='partial'):
        transport.click(0, 0, preflight=lambda: None)
    assert len(api.calls) == (2 if count == 2 else 1)
    if count == 2:
        assert len(api.calls[1]) == 1
        assert api.calls[1][0].mi.dwFlags == native.LEFTUP


def test_failed_cleanup_is_explicit_and_never_retries():
    api, transport = setup([1, 0])
    with pytest.raises(native.NativeInputError, match='release_failed'):
        transport.key_tap('Tab', preflight=lambda: None)
    transport.cancel()
    assert len(api.calls) == 2


def test_negative_virtual_desktop_pixel_centres():
    api, transport = setup()
    transport.click(-1920, -100, preflight=lambda: None)
    move, down, up = api.calls[0]
    assert move.mi.dwFlags == native.MOVE | native.ABSOLUTE | native.VIRTUALDESK
    assert (move.mi.dx, move.mi.dy) == (8, 27)
    assert down.mi.dwFlags == native.LEFTDOWN
    assert up.mi.dwFlags == native.LEFTUP
    transport.click(1919, 1079, preflight=lambda: None)
    move = api.calls[1][0]
    assert (move.mi.dx * 3840 // 65536, move.mi.dy * 1180 // 65536) == (3839, 1179)


@pytest.mark.parametrize('point', [(-1921, 0), (1920, 0), (0, -101), (0, 1080), (True, 0), (0.5, 1)])
def test_outside_or_invalid_coordinates(point):
    api, transport = setup()
    with pytest.raises(ValueError):
        transport.click(*point, preflight=lambda: None)
    assert not api.calls


def test_cancel_does_not_block_on_active_send_and_stops_next_batch():
    api, transport = setup()
    entered, finish = threading.Event(), threading.Event()
    errors = []
    original = api.SendInput
    def blocked(*args):
        entered.set()
        assert finish.wait(2)
        return original(*args)
    api.SendInput = blocked
    def worker():
        try:
            transport.type_text('abc', preflight=lambda: None)
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(2)
        transport.cancel()
    finally:
        finish.set()
        thread.join(2)
    assert not thread.is_alive()
    assert len(api.calls) == 1
    assert len(errors) == 1 and 'stopped' in str(errors[0])


@pytest.mark.parametrize('count', [-1, 100, None, True])
def test_invalid_send_counts_stop_transport(count):
    api, transport = setup([count])
    with pytest.raises(native.NativeInputError, match='invalid_count'):
        transport.key_tap('Tab', preflight=lambda: None)
    assert len(api.calls) == 1
