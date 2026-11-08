"""Delivery contract with fictional state, without importing the desktop app."""
import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import desktop_delivery as delivery


def application(stop_word=False, result=True, error=None):
    trace = []
    voice = SimpleNamespace(interruption_epoch=7, capture_allowed=False)
    app = SimpleNamespace(session=SimpleNamespace(voice=voice), speech_epoch=7)

    @contextmanager
    def span(name):
        trace.append(('enter', name))
        try:
            yield
        finally:
            trace.append(('exit', voice.capture_allowed))

    def speak(text):
        assert voice.capture_allowed and app.speech_epoch == voice.interruption_epoch
        trace.append(('speak', text))
        if error:
            raise error
        return result

    voice.speak = speak
    app.observation = SimpleNamespace(
        emit=lambda *args: trace.append(('emit', args)), span=span)
    app.events = SimpleNamespace(put=lambda item: trace.append(('event', item)))
    app.stop_word_enabled = SimpleNamespace(is_set=lambda: stop_word)
    return app, trace


def test_interrupted_epoch_has_no_effect():
    app, trace = application()
    app.speech_epoch = 6
    assert delivery.say(app, 'validation_reply') is False
    assert trace == []
    assert not app.session.voice.capture_allowed


@pytest.mark.parametrize('stop_word', [False, True])
@pytest.mark.parametrize('result', [False, True])
def test_delivery_order_status_and_return(stop_word, result):
    app, trace = application(stop_word, result)
    assert delivery.say(app, 'validation_reply') is result
    assert trace == [
        ('emit', ('turn.reply', {'characters': 16}, {'text': 'validation_reply'})),
        ('event', ('text', ('Alice', 'validation_reply'))),
        ('event', ('status', 'Alice parle. Ecoute stop seule.' if stop_word
                   else 'Alice parle. Microphone ferme.')),
        ('enter', 'voice_delivery'), ('speak', 'validation_reply'), ('exit', False)]
    assert not app.session.voice.capture_allowed


def test_exception_closes_capture_and_span():
    error = RuntimeError('validation_failure')
    app, trace = application(error=error)
    with pytest.raises(RuntimeError) as raised:
        delivery.say(app, 'validation_reply')
    assert raised.value is error
    assert trace[-1] == ('exit', False)
    assert not app.session.voice.capture_allowed


def test_epoch_refreshed_before_speak():
    app, trace = application()
    app.observation.emit = lambda *args: setattr(app.session.voice, 'interruption_epoch', 8)
    assert delivery.say(app, 'validation_reply') is True
    assert app.speech_epoch == 8


def test_application_delegates_same_object_and_result(monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'laboratoire/scripts/alice_desktop.py'
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'Application')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'say']
    env = {}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), env)
    app = env['Application']()
    marker = object()
    callback = Mock(return_value=marker)
    monkeypatch.setattr(delivery, 'say', callback)
    assert app.say('validation_reply') is marker
    callback.assert_called_once_with(app, 'validation_reply')
