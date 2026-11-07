"""Fake reader processes only; never start PowerShell or inspect Windows."""
import io
import json
from pathlib import Path
import sys
import threading
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'laboratoire' / 'scripts'))
from native_uia_worker import UIAWorker


def start(responses):
    process = Mock()
    process.stdin = io.StringIO()
    process.stdout = io.StringIO(responses)
    process.poll.return_value = None
    process.terminate.side_effect = lambda: setattr(process.poll, 'return_value', 0)
    factory = Mock(return_value=process)
    worker = UIAWorker({'hwnd': 1, 'pid': 2}, popen=factory, timeout=0.2)
    return worker, process, factory


def line(identifier=1, data=None):
    return json.dumps({'id': identifier, 'ok': True, 'data': data or {'validation': True}}) + '\n'


def test_process_reused_with_correlated_requests_and_closed():
    worker, process, factory = start(line() + line(2))
    try:
        assert worker.request('read') == {'validation': True}
        assert worker.request('hit_test', x=-20, y=10) == {'validation': True}
        sent = [json.loads(s) for s in process.stdin.getvalue().splitlines()]
        assert sent == [{'id': 1, 'op': 'read'}, {'id': 2, 'op': 'hit_test', 'x': -20, 'y': 10}]
        factory.assert_called_once()
        assert factory.call_args.kwargs['stderr'] is not None
        command = factory.call_args.args[0]
        root = Path(__file__).resolve().parents[3]
        assert factory.call_args.kwargs['cwd'] == root
        assert command[5] == 'vision/laboratoire/native_uia_snapshot.ps1'
        assert (root / command[5]).is_file()
        assert command[-1] == '-Worker'
    finally: worker.close()
    process.terminate.assert_called_once()
    assert process.stdin.closed and process.stdout.closed


@pytest.mark.parametrize('response', ['', 'not json\n', line(99), '{"id":true,"ok":true,"data":{}}\n',
    '{"id":1,"ok":false,"error":"failed"}\n', '{"id":1,"ok":true,"data":[]}\n', 'x' * (2*1024**2+1)])
def test_invalid_worker_output_closes_without_retry(response):
    worker, process, factory = start(response)
    with pytest.raises(Exception): worker.request('read')
    process.terminate.assert_called_once()
    with pytest.raises(RuntimeError, match='closed'): worker.request('read')
    factory.assert_called_once()


def test_invalid_operation_does_not_send():
    worker, process, _ = start(line())
    try:
        with pytest.raises(ValueError): worker.request('execute')
        with pytest.raises(ValueError): worker.request('hit_test', x=True, y=0)
        assert process.stdin.getvalue() == ''
    finally: worker.close()


def test_write_failure_closes_reader():
    worker, process, _ = start(line())
    process.stdin.close()
    with pytest.raises(ValueError): worker.request('read')
    process.terminate.assert_called_once()


def test_silent_worker_is_terminated_on_deadline():
    released = threading.Event()
    class Silent:
        def readline(self, limit):
            released.wait(2)
            return ''
        def close(self): pass
    process = Mock(stdin=io.StringIO(), stdout=Silent())
    process.poll.return_value = None
    def terminate():
        process.poll.return_value = 0
        released.set()
    process.terminate.side_effect = terminate
    worker = UIAWorker({'hwnd': 1, 'pid': 2}, popen=lambda *a, **k: process, timeout=0.01)
    with pytest.raises(Exception): worker.request('read')
    process.terminate.assert_called_once()
    assert released.is_set()
