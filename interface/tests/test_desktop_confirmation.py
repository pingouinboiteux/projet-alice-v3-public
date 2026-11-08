"""Confirmation guards without a real window, application, memory or service."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import desktop_confirmation as confirmation


@pytest.fixture
def dialog(monkeypatch):
    clock = [100.0]
    stop = threading.Event()
    window = Mock()
    callbacks = {}
    buttons = {}
    scheduled = []
    parent = Mock()
    window.protocol.side_effect = lambda key, cb: callbacks.update({key: cb})
    window.bind.side_effect = lambda key, cb: callbacks.update({key: cb})
    window.after.side_effect = lambda delay, cb: scheduled.append(cb)
    monkeypatch.setattr(confirmation.time, 'monotonic', lambda: clock[0])
    factory = Mock(return_value=window)
    monkeypatch.setattr(confirmation.tk, 'Toplevel', factory)
    for name in ('Frame', 'Label', 'StringVar'):
        monkeypatch.setattr(confirmation.tk, name, Mock())
    monkeypatch.setattr(confirmation.scrolledtext, 'ScrolledText', Mock())

    def button(*args, text, command, **kwargs):
        buttons['accept' if text.startswith('Confirmer') else 'cancel'] = command
        return Mock()

    monkeypatch.setattr(confirmation.tk, 'Button', button)
    return SimpleNamespace(clock=clock, stop=stop, window=window, parent=parent,
                           factory=factory, buttons=buttons, callbacks=callbacks,
                           scheduled=scheduled)


@pytest.mark.parametrize('reason', ['stopped', 'expired'])
def test_rejected_before_creating_window(dialog, reason):
    if reason == 'stopped':
        dialog.stop.set()
    deadline = 99 if reason == 'expired' else 102
    assert not confirmation.confirm_details(dialog.parent, 'validation_request', dialog.stop, deadline)
    dialog.factory.assert_not_called()


@pytest.mark.parametrize('action,accepted', [
    ('accept', True), ('cancel', False), ('escape', False), ('close', False),
    ('stop', False), ('expire', False), ('late_accept', False),
    ('stopped_accept', False), ('stop_after_accept', False),
])
def test_confirmation_outcomes(dialog, action, accepted):
    def interact(*args):
        if action in ('stop', 'stopped_accept'):
            dialog.stop.set()
        if action in ('expire', 'late_accept'):
            dialog.clock[0] = 102
        if action in ('stop', 'expire'):
            dialog.scheduled.pop(0)()
        elif action == 'escape':
            dialog.callbacks['<Escape>'](None)
        elif action == 'close':
            dialog.callbacks['WM_DELETE_WINDOW']()
        else:
            dialog.buttons['cancel' if action == 'cancel' else 'accept']()
            if action == 'stop_after_accept':
                dialog.stop.set()
        # Repeated callbacks must not destroy or approve a completed dialog again.
        dialog.buttons['accept']()

    dialog.parent.wait_window.side_effect = interact
    assert confirmation.confirm_details(dialog.parent, 'validation_request', dialog.stop, 102) is accepted
    dialog.window.destroy.assert_called_once()


@pytest.mark.parametrize('length,duration', [(1599, 60), (1600, 300)])
@pytest.mark.parametrize('offset,accepted', [(-0.01, True), (0, False)])
def test_default_deadline_boundary(dialog, length, duration, offset, accepted):
    def interact(*args):
        dialog.clock[0] = 100 + duration + offset
        dialog.buttons['accept']()

    dialog.parent.wait_window.side_effect = interact
    assert confirmation.confirm_details(dialog.parent, 'x' * length, dialog.stop) is accepted
    dialog.window.destroy.assert_called_once()


def test_obsolete_request_closes_its_preview_without_approval(dialog):
    obsolete=threading.Event()
    def interact(*args):
        obsolete.set();dialog.scheduled.pop(0)();dialog.buttons['accept']()
    dialog.parent.wait_window.side_effect=interact
    assert not confirmation.confirm_details(dialog.parent,'validation_request',dialog.stop,102,
                                             cancelled=obsolete.is_set)
    dialog.window.destroy.assert_called_once()
