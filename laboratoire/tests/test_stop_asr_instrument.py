from unittest.mock import Mock
import wave

import pytest

from validation_stop_asr import CASES, run_cases


def fake_wav(path):
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x00\x10'*24000)


def test_six_real_protocol_requests_without_audio_output(tmp_path):
    voice = Mock()
    hearing = Mock()
    paths = []
    def synthesize(text):
        path = tmp_path/f'validation_{len(paths)}.wav'
        fake_wav(path)
        paths.append(path)
        return path, {'audio_seconds':1.0}
    voice.synthesize.side_effect = synthesize
    hearing.command.side_effect = [{'status':expected} for _, _, expected in CASES]
    rows = []
    run_cases(voice, hearing, rows.append, root=tmp_path)
    assert len(rows) == 6 and all(row['passed'] for row in rows)
    assert all(call.args == ('transcribe_stop',) for call in hearing.command.call_args_list)
    assert all(not path.exists() for path in paths)
    voice.speak.assert_not_called()


def test_invalid_asr_result_is_failure_and_audio_is_deleted(tmp_path):
    path = tmp_path/'validation_stop.wav'; fake_wav(path)
    voice = Mock(); voice.synthesize.return_value = (path, {'audio_seconds':1.0})
    hearing = Mock(); hearing.command.return_value = {'status':'error'}
    with pytest.raises(RuntimeError, match='Invalid'):
        run_cases(voice, hearing, Mock(), root=tmp_path)
    assert not path.exists()


def test_resampling_preserves_duration_and_matches_installed_asr_format(tmp_path):
    from validation_stop_asr import hearing_wav
    path = tmp_path/'validation_source.wav'; fake_wav(path)
    with wave.open(str(hearing_wav(path)), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert abs(wav.getnframes()-16000) <= 1
