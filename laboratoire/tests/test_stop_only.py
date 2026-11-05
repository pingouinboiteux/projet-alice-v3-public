"""No microphone, model, memory or sound is opened by these tests."""
import array
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hearing_link import Hearing
from stop_command import is_stop_command
from voice_link import ROOT, Voice


@pytest.mark.parametrize('text', ['stop', 'STOP !', 'Alice, stop.'])
def test_explicit_stop(text):
    assert is_stop_command(text)


@pytest.mark.parametrize('text', ['', 'grrr', 'ah mince', 'non stop',
    'stopper', 'je dois stop ici', 'Alice raconte quelque chose'])
def test_other_speech_is_ignored(text):
    assert not is_stop_command(text)


def test_stop_surveillance_discards_everything_except_stop():
    hearing = Hearing(Mock())
    voice = Mock()
    heard_stop = __import__('threading').Event()
    voice.interrupt.side_effect = heard_stop.set
    hearing.command = Mock(side_effect=[{'status':'ignored'}, {'status':'stop'}])
    hearing.cancel = Mock()
    with hearing.stop_only(voice, enabled=True):
        assert heard_stop.wait(2)
    assert hearing.command.call_count == 2
    voice.interrupt.assert_called_once()


def test_disabled_surveillance_never_opens_hearing():
    hearing = Hearing(Mock())
    hearing.command = Mock()
    with hearing.stop_only(Mock()):
        pass
    hearing.command.assert_not_called()


def test_listener_reports_failure_while_voice_is_still_running():
    import threading
    hearing = Hearing(Mock())
    hearing.command = Mock(return_value={'status':'error'})
    hearing.cancel = Mock()
    failed = threading.Event()
    states = []
    def state(value):
        states.append(value)
        if value == 'error': failed.set()
    with pytest.raises(RuntimeError, match='Ecoute stop indisponible'):
        with hearing.stop_only(Mock(), enabled=True, on_status=state):
            assert failed.wait(2)
            assert 'requested' in states


def test_worker_error_is_diagnosed_without_recording_its_text():
    hearing = Hearing(Mock())
    hearing.process = Mock(); hearing.process.poll.return_value = None
    hearing.write_lock = __import__('threading').Lock()
    hearing.receive = Mock(return_value={'id':1, 'status':'error',
        'error_type':'RuntimeError', 'error_code':'input_overflow',
        'error':'sensitive detail', 'text':'private speech'})
    with patch('hearing_link.emit') as observer:
        assert hearing.command('stop_only') == {'status':'error'}
    metrics = observer.call_args.args[2]
    assert metrics['error_code'] == 'input_overflow'
    assert 'sensitive' not in repr(metrics) and 'private' not in repr(metrics)


def test_dynamic_microphone_disable_cancels_pending_capture_without_reopening():
    import threading
    hearing = Hearing(Mock())
    disabled = threading.Event()
    entered = threading.Event()
    cancelled = threading.Event()
    voice = Mock()
    def command(op, cancel_if):
        entered.set()
        assert disabled.wait(2)
        assert cancel_if()
        cancelled.set()
        return {'status':'stop'}  # Late ASR result must not interrupt playback.
    hearing.command = Mock(side_effect=command)
    hearing.cancel = Mock()
    with hearing.stop_only(voice, enabled=True, cancel_if=disabled.is_set):
        assert entered.wait(2)
        disabled.set()
        assert cancelled.wait(2)
    hearing.command.assert_called_once()
    voice.interrupt.assert_not_called()


def test_stuck_stop_reader_kills_worker_before_it_can_be_reused():
    hearing = Hearing(Mock())
    hearing.process = Mock(); hearing.process.poll.return_value = None
    hearing.cancel = Mock()
    with patch('hearing_link.threading.Thread') as factory:
        factory.return_value.is_alive.return_value = True
        with pytest.raises(RuntimeError, match='non terminee'):
            with hearing.stop_only(Mock(), enabled=True):
                pass
    hearing.process.terminate.assert_called_once()
    hearing.process.wait.assert_called_once_with(timeout=10)


def test_listener_is_entered_after_reset_and_can_interrupt_before_audio():
    from contextlib import contextmanager
    voice = Voice(Mock())
    @contextmanager
    def listener():
        voice.interrupt()
        yield
    voice.stop_listener = listener
    voice._speak = Mock(side_effect=lambda text: not voice.interrupted.is_set())
    assert voice.speak('validation') is False


def test_stop_command_does_not_expose_transcript_even_with_diagnostics():
    hearing = Hearing(Mock())
    hearing.process = Mock(); hearing.process.poll.return_value = None
    hearing.write_lock = __import__('threading').Lock()
    hearing.receive = Mock(return_value={'id':1, 'status':'ignored',
                                       'text':'private grumbling'})
    with patch('hearing_link.emit') as observer:
        assert hearing.command('stop_only') == {'status':'ignored'}
    observer.assert_called_once()
    assert 'private grumbling' not in repr(observer.call_args)
    assert observer.call_args.args[1] == 'hearing.stop_result'


def test_stop_callback_runs_once_per_interruption():
    voice = Voice(Mock())
    voice.on_interrupt = Mock()
    voice.interrupt()
    voice.interrupt()
    voice.on_interrupt.assert_called_once()


def test_interrupted_pcm_is_aborted_request_drained_and_next_reply_works():
    from sopro_protocol import render_pcm
    with tempfile.TemporaryDirectory(prefix='validation_stop_', dir=ROOT/'logs') as name:
        folder = Path(name)
        session = Mock(); session.observer = None
        session.temp = SimpleNamespace(name=name)
        voice = Voice(session); voice.continuous_playback = True
        voice.process = Mock(); voice.process.poll.return_value = None
        raw = array.array('h', [2000]*120000).tobytes()
        def request(line):
            data = json.loads(line)
            render_pcm([raw], data['id'], folder, ROOT, voice.messages.put, stream=True)
        voice.process.stdin.write.side_effect = request
        stream = Mock()
        stream.write.side_effect = lambda data: (voice.interrupt() or False)
        with patch.dict('sys.modules', sounddevice=SimpleNamespace(RawOutputStream=Mock(return_value=stream))):
            assert voice.speak('Premiere reponse fictive.') is False
            stream.abort.assert_called_once()
            stream.stop.assert_not_called()
            assert stream.write.call_count == 1
            assert voice.messages.empty()
            assert not list(folder.glob('*.wav'))
            stream.reset_mock()
            stream.write.side_effect = None
            stream.write.return_value = False
            assert voice.speak('Deuxieme reponse fictive.') is True
            stream.stop.assert_called_once()
            stream.abort.assert_not_called()
        voice.process.terminate.assert_not_called()
