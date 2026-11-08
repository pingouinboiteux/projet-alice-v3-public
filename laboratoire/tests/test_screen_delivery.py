import queue
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
from screen_delivery import deliver


def app(public=False):
    voice=Mock(capture_allowed=True,subtitles=object())
    return NS(stop=threading.Event(),paused=threading.Event(),events=queue.Queue(),
        channels=NS(enabled={'twitch':public}),initiative=NS(public_boundary=False),
        session=NS(voice=voice),confirm=Mock(return_value=False))


def test_passive_private_voice_has_no_subtitles_or_recording():
    a=app();voice=a.session.voice;original=voice.subtitles
    def speak(text):
        assert voice.subtitles is None and voice.capture_allowed is False
        return True
    voice.speak.side_effect=speak
    assert deliver(a,'validation_remarque',passive=True)
    assert voice.subtitles is original and voice.capture_allowed is True
    a.confirm.assert_not_called()


def test_public_passive_only_text_and_no_confirmation_spam():
    a=app(True);assert not deliver(a,'validation_remarque',passive=True)
    a.session.voice.speak.assert_not_called();a.confirm.assert_not_called()


def test_requested_public_reply_requires_approval():
    a=app(True);assert not deliver(a,'validation_constat')
    a.session.voice.speak.assert_not_called();a.confirm.assert_called_once()


def test_cancelled_reply_has_no_output():
    a=app();assert not deliver(a,'validation',cancelled=lambda:True)
    assert a.events.empty();a.session.voice.speak.assert_not_called()


def test_voice_failure_restores_privacy_flags():
    import pytest
    a=app();original=a.session.voice.subtitles
    a.session.voice.speak.side_effect=RuntimeError('validation')
    with pytest.raises(RuntimeError):deliver(a,'validation')
    assert a.session.voice.subtitles is original and a.session.voice.capture_allowed
