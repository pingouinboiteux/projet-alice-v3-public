"""Silent synthesis/file-hearing lifecycle, with no real workers or devices."""
import sys
import types
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import observer_natural_bench as bench


def fixtures(monkeypatch, tmp_path, *, sample_rate=24000, synthesis_error=False):
    events = []
    session = types.SimpleNamespace(temp=types.SimpleNamespace(name=str(tmp_path)), voice=None)

    class Voice:
        def __init__(self, owner):
            assert owner is session
        def start(self):
            events.append('voice.start')
            if synthesis_error:
                raise RuntimeError('synthesis unavailable')
        def audio_parts(self, text):
            events.append(('synthesize', text))
            path = tmp_path / 'validation_part.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(b'\x00\x00' * sample_rate)
            try:
                yield path, {}
            finally:
                path.unlink(missing_ok=True)
        def close(self):
            events.append('voice.close')

    class Hearing:
        def __init__(self, owner):
            assert owner is session
        def start(self):
            events.append('hearing.start')
        def command(self, op, **kwargs):
            assert op == 'transcribe'  # Never listen, device, or microphone operations.
            assert kwargs['validate_capture'] is True
            with wave.open(str(tmp_path / kwargs['file']), 'rb') as wav:
                assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
            events.append(('transcribe', kwargs['file']))
            return {'status': 'transcribed', 'accepted': True, 'cleaned': 'cree une note'}
        def close(self):
            events.append('hearing.close')

    monkeypatch.setitem(sys.modules, 'voice_link', types.SimpleNamespace(Voice=Voice))
    monkeypatch.setitem(sys.modules, 'hearing_link', types.SimpleNamespace(Hearing=Hearing))
    monkeypatch.setattr(bench, 'ROOT', tmp_path)
    return session, events


def test_silent_file_path_converts_and_cleans_audio(monkeypatch, tmp_path):
    session, events = fixtures(monkeypatch, tmp_path)
    rows = bench.silent_hearing(session, ['Alice, cree une note.'])
    assert rows[0]['heard']['accepted'] is True
    assert events.index('voice.close') < events.index('hearing.start')
    assert events[-1] == 'hearing.close'
    assert session.voice is None
    assert list(tmp_path.glob('*.wav')) == []


def test_unexpected_audio_format_fails_without_starting_hearing(monkeypatch, tmp_path):
    session, events = fixtures(monkeypatch, tmp_path, sample_rate=22050)
    with pytest.raises(RuntimeError, match='Unexpected synthesis format'):
        bench.silent_hearing(session, ['Alice'])
    assert 'hearing.start' not in events
    assert 'voice.close' in events
    assert 'hearing.close' in events


def test_failed_voice_start_closes_both_wrappers(monkeypatch, tmp_path):
    session, events = fixtures(monkeypatch, tmp_path, synthesis_error=True)
    with pytest.raises(RuntimeError, match='synthesis unavailable'):
        bench.silent_hearing(session, ['Alice'])
    assert 'voice.close' in events
    assert 'hearing.close' in events
    assert session.voice is None
