"""Callbacks and confirmation lifecycle without Tk, services or real input."""
import ast
from contextlib import nullcontext
from pathlib import Path
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import desktop_commands as commands


def application():
    # Load only the application methods: no module imports or constructor run.
    source = Path(__file__).resolve().parents[2] / 'laboratoire/scripts/alice_desktop.py'
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'Application')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                and n.name in {'submit', 'confirm', 'poll', 'shutdown'}]
    platform = SimpleNamespace(windll=SimpleNamespace(user32=Mock()))
    platform.windll.user32.GetAsyncKeyState.return_value = 0
    clock = SimpleNamespace(monotonic=lambda: 10)
    env = dict(threading=threading, time=clock, ctypes=platform,
               MEMORY_CONFIRM_SECONDS=120, ACTION_CONFIRM_SECONDS=30,
               confirm_details=Mock(return_value=True))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), env)
    app = env['Application']()
    for name in ('window', 'observation', 'observation_status', 'diagnostic_enabled',
                 'history', 'status', 'stop_status', 'resources', 'external_status',
                 'pause_button', 'entry', 'note_pending', 'initiative', 'hearing'):
        setattr(app, name, Mock())
    app.observation.io_error = None
    app.observation.span.return_value = nullcontext()
    app.stop, app.finished, app.paused = (threading.Event() for _ in range(3))
    app.events, app.inputs = queue.Queue(), queue.Queue()
    app.confirmations, app.external_states = [], {}
    app.session = None
    app.append = Mock()
    return app, env


def test_submit_limits_input_cancels_pending_and_hearing():
    app, _ = application()
    app.entry.get.return_value = ' ' + 'x' * 6000 + ' '
    app.submit()
    assert app.inputs.get_nowait() == 'x' * 5000
    app.note_pending.cancel.assert_called_once()
    app.hearing.cancel.assert_called_once()
    app.stop.set()
    app.submit()
    assert app.inputs.empty()


@pytest.mark.parametrize('stop,expired,accepted', [(False, False, True),
    (True, False, False), (False, True, False)])
def test_poll_confirmation_lifecycle(stop, expired, accepted):
    app, env = application()
    event, result = threading.Event(), []
    if stop:
        app.stop.set()
    if expired:
        event.set()
    app.events.put(('confirm', ('validation_request', event, result, 40)))
    app.poll()
    assert event.is_set()
    assert result == ([] if expired else [accepted])
    assert app.confirmations == []
    assert env['confirm_details'].call_count == int(not stop and not expired)
    app.window.after.assert_called_once_with(100, app.poll)


def test_shutdown_during_dialog_cannot_accept_and_closes_when_finished():
    app, env = application()
    event, result = threading.Event(), []
    app.events.put(('confirm', ('validation_request', event, result, 40)))
    env['confirm_details'].side_effect = lambda *args,**kwargs: (app.shutdown(), True)[1]
    app.poll()
    assert result == [False]
    assert event.is_set() and app.stop.is_set()
    app.finished.set()
    app.poll()
    app.window.destroy.assert_called_once()


def test_confirm_worker_uses_queue_and_returns_dialog_result():
    app, env = application()
    real_put = app.events.put
    def process(item):
        real_put(item)
        app.poll()
    app.events.put = process
    assert app.confirm('validation_request') is True
    app.observation.emit.assert_any_call('confirmation.result',
                                         {'accepted': True, 'expired': False})


def test_new_input_cancels_confirmation_without_nested_public_reply():
    app,env=application()
    app.channels=Mock()
    app.session=SimpleNamespace(voice=Mock())
    app.inputs.put('validation_nouvelle_demande')
    assert app.confirm('validation_request') is False
    app.channels.handle_one.assert_not_called()
    assert app.events.get_nowait()[1][1].is_set()


def test_approval_becomes_invalid_if_user_changes_request_in_dialog():
    app,env=application()
    real_put=app.events.put
    def process(item):
        real_put(item);app.poll();app.inputs.put('validation_nouvelle_demande')
    app.events.put=process
    assert app.confirm('validation_request') is False


def test_poll_dispatch_and_f12_keep_shutdown_owner():
    app, env = application()
    for item in [('text', ('Alice', 'validation_text')), ('resources', 'validation_cpu'),
                 ('pause', None), ('remote_status', ('twitch', 'ready'))]:
        app.events.put(item)
    app.poll()
    app.append.assert_called_once_with('Alice', 'validation_text')
    app.resources.set.assert_called_once_with('validation_cpu')
    assert app.paused.is_set()
    assert app.external_states == {'twitch': 'connecte'}
    env['ctypes'].windll.user32.GetAsyncKeyState.return_value = 0x8000
    app.poll()
    assert app.stop.is_set()
