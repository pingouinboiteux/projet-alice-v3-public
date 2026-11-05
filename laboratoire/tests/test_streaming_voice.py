import array
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock,patch
import wave
import pytest

from voice_protocol import render
from voice_link import Voice,VoiceRequestError,ROOT
from alice.voice.text import chunks,sentences


@pytest.fixture
def folder():
    with tempfile.TemporaryDirectory(prefix='validation_stream_',dir=ROOT/'logs') as name:
        yield Path(name)


TEXT='Cette premiere phrase contient assez de mots pour etre decoupee en plusieurs morceaux de synthese. Une seconde phrase arrive ensuite.'


def test_first_whole_sentence_published_before_remaining_synthesis_with_identical_pcm(folder):
    calls=[];events=[]
    def synth(part):
        calls.append(part)
        return array.array('h',[len(calls)*1000]*4800)
    def send(event):
        events.append(event)
        if event['status']=='audio_part' and event['part']==0:
            assert ' '.join(calls)==sentences(TEXT)[0]
            assert len(calls)<len(chunks(TEXT))
            with wave.open(str(ROOT/event['file']),'rb') as wav:
                assert wav.getnframes()==4800*len(calls)
    render(TEXT,1,folder,ROOT,synth,chunks,sentences,send,True)
    stream_pcm=b''
    for event in events[:-1]:
        with wave.open(str(ROOT/event['file']),'rb') as wav: stream_pcm+=wav.readframes(wav.getnframes())
    assert events[-1]['status']=='audio_end'
    calls.clear();full=[]
    render(TEXT,2,folder,ROOT,synth,chunks,sentences,full.append,False)
    with wave.open(str(ROOT/full[0]['file']),'rb') as wav: normal_pcm=wav.readframes(wav.getnframes())
    assert stream_pcm==normal_pcm


def fake_voice(folder):
    session=Mock();session.observer=None;session.temp=SimpleNamespace(name=str(folder))
    voice=Voice(session)
    voice.process=Mock();voice.process.poll.return_value=None
    return voice


def test_parent_playback_order_and_cleanup_without_sound(folder):
    voice=fake_voice(folder)
    def write(line):
        request=json.loads(line)
        render(TEXT,request['id'],folder,ROOT,lambda _:array.array('h',[1000]*4800),
               chunks,sentences,voice.messages.put,True)
    voice.process.stdin.write.side_effect=write
    played=[]
    with patch('winsound.PlaySound',side_effect=lambda name,flags:played.append(name) if name else None):
        voice.speak(TEXT)
    assert len(played)==2
    assert not list(folder.glob('*.wav'))
    voice.process.terminate.assert_not_called()


def test_terminal_synthesis_error_does_not_poison_next_request(folder):
    voice=fake_voice(folder)
    def fail(line):
        request=json.loads(line)
        voice.messages.put({'status':'error','id':request['id'],'error':'invalid duration'})
    voice.process.stdin.write.side_effect=fail
    with pytest.raises(VoiceRequestError): list(voice.audio_parts(TEXT))
    voice.process.terminate.assert_not_called()
    def success(line):
        request=json.loads(line)
        render(TEXT,request['id'],folder,ROOT,lambda _:array.array('h',[1000]*4800),
               chunks,sentences,voice.messages.put,True)
    voice.process.stdin.write.side_effect=success
    assert len(list(voice.audio_parts(TEXT)))==2
    assert not list(folder.glob('*.wav'))


def test_invalid_sequence_stops_worker_and_cleans_request(folder):
    voice=fake_voice(folder)
    voice.messages.put({'status':'audio_part','id':999,'part':0})
    with pytest.raises(RuntimeError,match='Sequence'): list(voice.audio_parts(TEXT))
    voice.process.terminate.assert_called_once()


def test_failed_later_synthesis_never_publishes_unfinished_audio(folder):
    calls=[];events=[]
    def synth(text):
        calls.append(text)
        if len(calls)==len(chunks(TEXT)): raise RuntimeError('invalid duration')
        return array.array('h',[1000]*4800)
    with pytest.raises(RuntimeError): render(TEXT,1,folder,ROOT,synth,chunks,sentences,events.append,True)
    assert len(events)==1 and events[0]['status']=='audio_part'
    assert len(list(folder.glob('*.wav')))==1


def test_premature_terminal_record_is_not_reported_complete(folder):
    voice=fake_voice(folder)
    def write(line):
        request=json.loads(line);events=[]
        render(TEXT,request['id'],folder,ROOT,lambda _:array.array('h',[1000]*4800),
               chunks,sentences,events.append,True)
        voice.messages.put(events[0])
        voice.messages.put({'id':request['id'],'status':'audio_end','parts':1})
    voice.process.stdin.write.side_effect=write
    with pytest.raises(RuntimeError,match='Fin vocale'): list(voice.audio_parts(TEXT))
    voice.process.terminate.assert_called_once()
    assert not list(folder.glob('*.wav'))
