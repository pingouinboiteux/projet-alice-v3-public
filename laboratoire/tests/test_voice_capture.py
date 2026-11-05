import array
import hashlib
import json
import time
import wave

import pytest

from voice_capture import arm, begin, purge, NAMES


def test_one_authorized_reply_preserves_pcm_and_is_purged(tmp_path):
    arm(tmp_path)
    capture=begin('sopro_d',tmp_path)
    assert begin('sopro_d',tmp_path) is None
    raw=array.array('h',[1200,-1300]*6000).tobytes()
    packet=tmp_path/'validation_packet.wav'
    with wave.open(str(packet),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed')); wav.writeframes(raw)
    capture.append(packet); capture.append(packet)
    capture.close(True,0,{'name':'validation_headset'})
    with wave.open(str(tmp_path/NAMES[1]),'rb') as wav:
        assert wav.readframes(wav.getnframes()) == raw+raw
    report=json.loads((tmp_path/NAMES[2]).read_text())
    assert report['pcm_sha256'] == hashlib.sha256(raw+raw).hexdigest()
    assert report['complete'] and report['packets']==2 and not report['microphone_recorded']
    purge(tmp_path)
    assert not any((tmp_path/name).exists() for name in NAMES)


def test_no_recording_without_permission_or_after_expiration(tmp_path):
    assert begin('sopro_d',tmp_path) is None
    arm(tmp_path)
    with pytest.raises(RuntimeError): arm(tmp_path)
    (tmp_path/NAMES[0]).write_text(json.dumps({'expires_at':time.time()-1}))
    assert begin('sopro_d',tmp_path) is None
    assert not any((tmp_path/name).exists() for name in NAMES)


def test_purge_while_playing_does_not_recreate_the_recording(tmp_path):
    arm(tmp_path)
    capture=begin('sopro_d',tmp_path)
    purge(tmp_path)
    capture.append(tmp_path/'does_not_exist.wav')
    capture.close(True,0,{})
    assert not any((tmp_path/name).exists() for name in NAMES)


def test_clear_observation_also_erases_authorized_audio(tmp_path, monkeypatch):
    import observation
    folder=tmp_path/'validation_audio_observer'
    monkeypatch.setattr(observation, 'LIVE', folder/'live.json')
    observer=observation.Observation(folder=folder, background=False)
    arm(folder)
    capture=begin('sopro_d',folder)
    observer.purge()
    capture.close(True,0,{})
    observer.close()
    assert not any((folder/name).exists() for name in NAMES)
