"""Real capture loop with synthetic frames: no microphone or ASR model."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from hearing_capture_loop import capture_input


def test_public_arrival_during_speech_preserves_the_complete_utterance():
    stream=Mock();stream.read.return_value=(np.zeros((480,1),dtype=np.int16),False)
    vad=Mock();vad.predict.side_effect=[1,1,0]
    capture=Mock();capture.active=True
    result=SimpleNamespace(audio=np.ones(960),end_reason='silence')
    capture.feed.side_effect=[None,None,result]
    pending=threading.Event();pending.set()
    audio,reason,ended=capture_input(stream,capture,vad,np,.5,threading.Event(),pending,time.monotonic())
    assert audio is result.audio and reason=='silence' and ended is not None
    assert stream.read.call_count==3


def test_public_arrival_wakes_silence_without_waiting_for_ten_second_timeout():
    stream=Mock();stream.read.return_value=(np.zeros((480,1),dtype=np.int16),False)
    vad=Mock();vad.predict.return_value=0
    capture=Mock();capture.active=False;capture.feed.return_value=None
    pending=threading.Event();pending.set()
    assert capture_input(stream,capture,vad,np,.5,threading.Event(),pending,time.monotonic())==(None,None,None)
    stream.read.assert_called_once()
