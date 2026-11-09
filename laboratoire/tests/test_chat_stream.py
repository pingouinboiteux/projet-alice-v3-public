"""Local stream assembly and cancellation, without opening a model or network."""
import json
import threading
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from chat import Session
from screen_model import analyze


def event(content='', finish=None):
    return ('data: ' + json.dumps({'choices': [{'delta': {'content': content},
        'finish_reason': finish}]}) + '\n').encode('utf-8')


class Stream:
    def __init__(self, lines, on_line=lambda _: None):
        self.lines = list(lines)
        self.on_line = on_line
        self.index = 0
        self.closed = False

    def __enter__(self):return self
    def __exit__(self, *_):self.closed = True
    def __iter__(self):return self

    def __next__(self):
        if self.index >= len(self.lines):raise StopIteration
        self.on_line(self.index)
        line = self.lines[self.index]
        self.index += 1
        return line


def fake_session(stream):
    opener = SimpleNamespace(open=Mock(return_value=stream))
    return SimpleNamespace(check=Mock(), url='http://127.0.0.1:12345',
                           key='validation_key', opener=opener)


def test_stream_reassembles_content_and_preserves_finish_reason():
    stream = Stream([event('{"ok":'), event('true}', 'stop'), b'data: [DONE]\n'])
    session = fake_session(stream)
    result = Session.request_stream_cancelable(session, '/v1/chat/completions',
        {'messages': []}, cancelled=lambda: False)
    assert result == {'choices': [{'finish_reason': 'stop',
                                   'message': {'content': '{"ok":true}'}}]}
    assert stream.closed
    request = session.opener.open.call_args.args[0]
    assert json.loads(request.data)['stream'] is True
    assert request.get_header('Authorization') == 'Bearer validation_key'


def test_cancel_closes_stream_before_late_content_is_accepted():
    cancelled = [False]
    stream = Stream([event('{"ok":'), event('false}', 'stop')],
                    on_line=lambda index: cancelled.__setitem__(0, True) if index == 1 else None)
    session = fake_session(stream)
    assert Session.request_stream_cancelable(session, '/v1/chat/completions',
        {'messages': []}, cancelled=lambda: cancelled[0]) is None
    assert stream.closed


def test_stream_without_finish_is_rejected():
    session = fake_session(Stream([event('partial')]))
    with pytest.raises(ValueError, match='Incomplete model stream'):
        Session.request_stream_cancelable(session, '/v1/chat/completions',
            {'messages': []}, cancelled=lambda: False)


def test_passive_vision_uses_cancelable_stream_without_model_or_image_library():
    class FakeImage:
        def copy(self):return FakeImage()
        def thumbnail(self, *_):pass
        def save(self, output, format):
            assert format == 'PNG'
            output.write(b'validation_image')
        def close(self):pass

    value={'description':'validation_scene','reaction':'','notable':False,'uncertain':False}
    session=SimpleNamespace(vision_enabled=True,inference_lock=threading.RLock(),
        request=Mock(),request_stream_cancelable=Mock(return_value={
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}))
    assert analyze(session,FakeImage(),'validation_question',passive=True)==value
    session.request.assert_not_called()
    session.request_stream_cancelable.assert_called_once()
