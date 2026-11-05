"""Real frame loop and capture state, synthetic input only; never opens a mic."""
import threading
import time
from unittest.mock import Mock

import numpy as np
import pytest

from alice.hearing.capture import SpeechCapture
from hearing_capture_loop import capture_input


def fresh_capture():
    return SpeechCapture(minimum_speech_seconds=.15, short_silence_seconds=.3,
                         fixed_silence_seconds=.4, maximum_silence_seconds=.6,
                         maximum_utterance_seconds=3)


def run(stream, vad, restart=None, cancelled=None):
    return capture_input(stream, fresh_capture(), vad, np, .5,
                         cancelled or threading.Event(), threading.Event(),
                         time.monotonic(), restart_capture=restart)


def frame(value=0, overflow=False):
    return np.full((480, 1), value, dtype=np.int16), overflow


def test_stop_recovers_from_overflow_without_reusing_damaged_fragment():
    stream = Mock()
    stream.read.side_effect = ([frame(1000)] * 3 + [frame(2000, True)]
                               + [frame(3000)] * 5 + [frame()] * 13)
    vad = Mock()
    vad.predict.side_effect = [1] * 8 + [0] * 13
    restart = Mock(side_effect=fresh_capture)
    audio, reason, ended = run(stream, vad, restart)
    restart.assert_called_once()
    assert reason == 'silence' and ended is not None
    assert len(audio) == 18 * 480
    assert not np.any(audio == np.float32(1000 / 32768))
    assert np.all(audio[:5 * 480] == np.float32(3000 / 32768))


def test_normal_listening_still_rejects_incomplete_audio():
    stream = Mock(); stream.read.return_value = frame(1, True)
    with pytest.raises(RuntimeError, match='Capture micro incomplete'):
        run(stream, Mock())


def test_five_consecutive_overflows_fail_with_explicit_error():
    stream = Mock(); stream.read.return_value = frame(1, True)
    restart = Mock(side_effect=fresh_capture)
    with pytest.raises(RuntimeError, match='debordements micro repetes'):
        run(stream, Mock(), restart)
    assert stream.read.call_count == 5
    assert restart.call_count == 4


def test_healthy_frame_resets_consecutive_overflow_limit():
    stream = Mock()
    stream.read.side_effect = ([frame(1, True)] * 4 + [frame()]
                               + [frame(1, True)] * 4
                               + [frame(3000)] * 5 + [frame()] * 13)
    vad = Mock(); vad.predict.side_effect = [0] + [1] * 5 + [0] * 13
    restart = Mock(side_effect=fresh_capture)
    audio, reason, _ = run(stream, vad, restart)
    assert audio is not None and reason == 'silence'
    assert restart.call_count == 8


def test_cancellation_after_overflow_does_not_retry_capture():
    cancelled = threading.Event()
    stream = Mock(); stream.read.return_value = frame(1, True)
    def restart():
        cancelled.set()
        return fresh_capture()
    assert run(stream, Mock(), restart, cancelled) == (None, None, None)
    stream.read.assert_called_once()
