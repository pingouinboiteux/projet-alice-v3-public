import array
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wave

import pytest

from voice_output_comparison import play, PROFILES


def fixture_audio(folder):
    raw=array.array('h',[-32768,-1200,0,1300,32767]*12000).tobytes()
    with wave.open(str(folder/'voice_capture.wav'),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed')); wav.writeframes(raw)
    (folder/'voice_capture.json').write_text(json.dumps({'pcm_sha256':hashlib.sha256(raw).hexdigest()}))
    return raw


def test_comparison_replays_same_captured_signal_without_changing_source(tmp_path):
    raw=fixture_audio(tmp_path)
    original=(tmp_path/'voice_capture.wav').read_bytes()
    for command in PROFILES:
        stream=Mock(); stream.write.return_value=False
        with patch('voice_load_probe.SilentSynthesis') as load:
            load.return_value.report={'requests':1,'packets':2,'finished':True,'error_type':None}
            play(SimpleNamespace(check=Mock()),command,tmp_path,Mock(return_value=stream))
            if command in {'/sortie-e','/sortie-f'}:
                load.return_value.start.assert_called_once()
                load.return_value.close.assert_called_once()
            else: load.assert_not_called()
        output=b''.join(c.args[0] for c in stream.write.call_args_list)
        if PROFILES[command]=='mme_mono': assert output==raw
        else:
            samples=array.array('h'); samples.frombytes(output)
            assert samples[::2].tobytes()==raw and samples[1::2].tobytes()==raw
        stream.start.assert_called_once(); stream.stop.assert_called_once()
    assert (tmp_path/'voice_capture.wav').read_bytes()==original
    assert len(json.loads((tmp_path/'voice_output_test.json').read_text()))==len(PROFILES)
    assert not list(tmp_path.glob('validation_packet_replay_*'))


def test_changed_recording_is_rejected_before_audio_device_open(tmp_path):
    fixture_audio(tmp_path)
    (tmp_path/'voice_capture.json').write_text(json.dumps({'pcm_sha256':'wrong'}))
    factory=Mock()
    with pytest.raises(RuntimeError,match='change'):
        play(SimpleNamespace(check=Mock()),'/sortie-a',tmp_path,factory)
    factory.assert_not_called()


def test_silent_generation_drains_request_and_stops_without_playback():
    from voice_load_probe import SilentSynthesis
    finished=[]
    def parts(_):
        yield 'validation_not_played_1.wav',{}
        yield 'validation_not_played_2.wav',{}
        finished.append(True)
    session=SimpleNamespace(check=Mock(),voice=SimpleNamespace(audio_parts=parts))
    load=SilentSynthesis(session)
    load.start(); load.close()
    assert load.report['finished'] and load.report['error_type'] is None
    assert load.report['requests']==len(finished)>=1
    assert load.report['packets']==2*len(finished)
    assert not load.thread.is_alive()


def test_incomplete_comparison_records_error_type(tmp_path):
    fixture_audio(tmp_path)
    stream=Mock(); stream.start.side_effect=RuntimeError('validation failure')
    with pytest.raises(RuntimeError):
        play(SimpleNamespace(check=Mock()),'/sortie-a',tmp_path,Mock(return_value=stream))
    report=json.loads((tmp_path/'voice_output_test.json').read_text())['/sortie-a']
    assert not report['complete'] and report['error_type']=='RuntimeError'
