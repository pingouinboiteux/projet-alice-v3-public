import sys
import types
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import observer_audio_diagnosis as diagnosis


def setup(monkeypatch, tmp_path, *, fail_command=False, bad_format=False):
    folder = tmp_path / 'validation_pair_test'
    folder.mkdir()
    session = types.SimpleNamespace(temp=types.SimpleNamespace(name=str(folder)), voice=None, check=Mock())
    events = []

    class Voice:
        def __init__(self, owner):
            assert owner is session
        def start(self):
            events.append('voice.start')
        def audio_parts(self, text):
            part = folder / 'validation_part.wav'
            with wave.open(str(part), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2)
                wav.setframerate(22050 if bad_format else 24000)
                wav.writeframes(b'\x00\x00' * 2400)
            try:
                yield part, {}
            finally:
                part.unlink(missing_ok=True)
        def close(self):
            events.append('voice.close')

    class Hearing:
        def __init__(self, owner):
            assert owner is session
        def start(self):
            events.append('hearing.start')
        def command(self, op, **kwargs):
            assert op == 'transcribe'
            assert type(kwargs['validate_capture']) is bool
            path = tmp_path / kwargs['file']
            raw = path.read_bytes()
            with wave.open(str(path), 'rb') as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
            events.append((kwargs['file'], kwargs['validate_capture'], raw))
            if fail_command:
                raise RuntimeError('ASR unavailable')
            return {'status': 'transcribed', 'text': 'Alice, test.', 'accepted': True, 'audio_seconds': .1}
        def close(self):
            events.append('hearing.close')

    monkeypatch.setitem(sys.modules, 'voice_link', types.SimpleNamespace(Voice=Voice))
    monkeypatch.setitem(sys.modules, 'hearing_link', types.SimpleNamespace(Hearing=Hearing))
    monkeypatch.setattr(diagnosis, 'ROOT', tmp_path)
    return session, folder, events


def test_pairs_use_identical_bytes_and_no_microphone_operations(monkeypatch, tmp_path):
    session, folder, events = setup(monkeypatch, tmp_path)
    result = diagnosis.run_diagnosis(session)
    calls = [event for event in events if isinstance(event, tuple)]
    assert len(calls) == 8
    for index in range(0, 8, 2):
        assert calls[index][0] == calls[index+1][0]
        assert calls[index][2] == calls[index+1][2]
        assert {calls[index][1], calls[index+1][1]} == {True, False}
    assert result['rows'][0]['order'] == ['full_file', 'captured']
    assert result['rows'][1]['order'] == ['captured', 'full_file']
    assert all(row['same_words'] for row in result['rows'])
    assert events.index('voice.close') < events.index('hearing.start')
    assert result['status'] == 'complete'
    assert not list(folder.glob('*.wav'))
    assert session.voice is None


def test_asr_error_still_removes_all_prepared_files(monkeypatch, tmp_path):
    session, folder, events = setup(monkeypatch, tmp_path, fail_command=True)
    with pytest.raises(RuntimeError, match='ASR unavailable'):
        diagnosis.run_diagnosis(session)
    assert events[-1] == 'hearing.close'
    assert not list(folder.glob('*.wav'))
    assert session.voice is None


def test_bad_format_does_not_start_asr(monkeypatch, tmp_path):
    session, folder, events = setup(monkeypatch, tmp_path, bad_format=True)
    with pytest.raises(RuntimeError, match='Unexpected synthesis format'):
        diagnosis.run_diagnosis(session)
    assert 'hearing.start' not in events
    assert 'voice.close' in events and 'hearing.close' in events
    assert not list(folder.glob('*.wav'))


def test_guard_failure_starts_nothing(monkeypatch, tmp_path):
    session, folder, events = setup(monkeypatch, tmp_path)
    session.check.side_effect = RuntimeError('FPS')
    with pytest.raises(RuntimeError, match='FPS'):
        diagnosis.run_diagnosis(session)
    assert not events


def test_metric_never_repairs_homophones_digits_or_accents():
    assert diagnosis.compare_words('Alice, arroser!', 'alice ARROSER')['word_match']
    assert not diagnosis.compare_words('Arroser', 'Arroseur')['word_match']
    assert not diagnosis.compare_words('09:15', 'neuf heures quinze')['word_match']
    assert not diagnosis.compare_words('Été', 'Ete')['word_match']
    assert diagnosis.compare_words('un deux trois', 'un trois')['word_edit_distance'] == 1
