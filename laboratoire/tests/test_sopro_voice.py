import array
import json
import wave
import pytest
from sopro_protocol import render_pcm
from test_streaming_voice import folder,fake_voice
from voice_profile import selected_voice

def test_sopro_pcm_is_preserved_with_tiny_tail_and_unknown_part_count(folder):
    events=[]
    raw=array.array('h',[1000]*61001).tobytes()
    render_pcm((raw[:4000],raw[4000:-2],raw[-2:]),1,folder,folder,events.append)
    assert events[-1]['status']=='audio_end'
    assert events[-1]['parts']==len(events)-1
    result=b''
    for event in events[:-1]:
        assert event['parts'] is None
        with wave.open(str(folder/event['file']),'rb') as w:
            assert w.getnframes()>=2400
            result+=w.readframes(w.getnframes())
    assert result==raw

def test_parent_accepts_dynamic_parts_and_removes_files(folder):
    voice=fake_voice(folder)
    # Protocol paths must be relative to the actual laboratory root.
    from voice_link import ROOT
    def write(line):
        request=json.loads(line)
        render_pcm([array.array('h',[1000]*60000).tobytes()],request['id'],folder,ROOT,voice.messages.put)
    voice.process.stdin.write.side_effect=write
    assert len(list(voice.audio_parts('Bonjour.')))>=2
    assert not list(folder.glob('*.wav'))
    voice.process.terminate.assert_not_called()

def test_parent_rejects_wrong_dynamic_terminal_count(folder):
    voice=fake_voice(folder)
    from voice_link import ROOT
    def write(line):
        request=json.loads(line);events=[]
        render_pcm([array.array('h',[1000]*6000).tobytes()],request['id'],folder,ROOT,events.append)
        events[-1]['parts']=99
        for event in events:voice.messages.put(event)
    voice.process.stdin.write.side_effect=write
    with pytest.raises(RuntimeError,match='Fin vocale'):list(voice.audio_parts('Bonjour.'))
    voice.process.terminate.assert_called_once()

def test_pcm_limit_is_checked_before_publication(folder):
    with pytest.raises(ValueError,match='PCM'):render_pcm([b'1'],1,folder,folder,lambda _:None)
    assert not list(folder.glob('*.wav'))

def test_nonstreaming_returns_one_complete_file(folder):
    raw=array.array('h',[1000]*61001).tobytes();events=[]
    render_pcm([raw[:6000],raw[6000:]],2,folder,folder,events.append,stream=False)
    assert len(events)==1 and events[0]['status']=='audio' and events[0]['parts']==1
    with wave.open(str(folder/events[0]['file']),'rb') as wav:
        assert wav.readframes(wav.getnframes())==raw

def test_worker_failure_cannot_publish_a_false_end_record(folder):
    events=[]
    def broken():
        yield array.array('h',[1000]*30000).tobytes()
        raise RuntimeError('generation incomplete')
    with pytest.raises(RuntimeError):render_pcm(broken(),3,folder,folder,events.append)
    assert events and all(e['status']=='audio_part' for e in events)

def test_sopro_is_default_after_headset_acceptance_with_original_voice_available(monkeypatch):
    monkeypatch.delenv('ALICE_VOICE_ENGINE',raising=False)
    assert selected_voice()['worker']=='scripts/sopro_worker.py'
    assert selected_voice()['name']=='sopro_original'
    monkeypatch.setenv('ALICE_VOICE_ENGINE','current')
    assert selected_voice()['worker']=='scripts/voice_worker.py'
    monkeypatch.setenv('ALICE_VOICE_ENGINE','sopro_d')
    assert selected_voice()['worker']=='scripts/sopro_worker.py'
    monkeypatch.setenv('ALICE_VOICE_ENGINE','arbitrary')
    with pytest.raises(ValueError):selected_voice()


def test_original_sample_is_required_for_active_sopro(monkeypatch,tmp_path):
    import json
    import voice_profile
    folder=tmp_path/'config';folder.mkdir()
    config={'model':'models/voice/sopro','reference':'models/voice/reference_alice.wav','steps':2,'language':'fr'}
    path=folder/'voice-sopro.lock.json'
    path.write_text(json.dumps(config))
    monkeypatch.setattr(voice_profile,'ROOT',tmp_path)
    assert voice_profile.sopro_settings()['reference']=='models/voice/reference_alice.wav'
    config['reference']='models/voice/reference_sopro_d.wav';path.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='sample original'):voice_profile.sopro_settings()
