import json
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from observation import Observation, read_snapshot, assess, LIMIT, format_snapshot
from persistent_memory import Memory


@pytest.fixture
def tmp_path():
    logs=Path(__file__).resolve().parents[1]/'logs'
    with tempfile.TemporaryDirectory(prefix='validation_observer_tests_',dir=logs) as folder:
        path=Path(folder).resolve()
        assert path.is_relative_to(logs.resolve())
        yield path


def make(tmp_path,content=False,**kwargs):
    return Observation(content, tmp_path/'validation_observer',background=False,**kwargs)


def test_metadata_has_no_text_and_content_is_opt_in(tmp_path):
    observer=make(tmp_path)
    observer.begin_turn('PRIVATE_INPUT','text')
    observer.emit('memory.selected',{'selected':1},{'source':'PRIVATE_MEMORY'})
    observer.flush()
    assert 'PRIVATE' not in observer.path.read_text(encoding='utf8')
    observer.purge(content=True)
    observer.begin_turn('DIAGNOSTIC_INPUT','text')
    observer.flush()
    assert 'DIAGNOSTIC_INPUT' in observer.path.read_text(encoding='utf8')
    observer.purge(content=False)
    assert 'DIAGNOSTIC_INPUT' not in observer.path.read_text(encoding='utf8')
    observer.close()


def test_ring_disk_bound_and_no_archives(tmp_path):
    observer=make(tmp_path,True)
    for _ in range(500): observer.emit('turn.reply',detail={'text':'X'*30000})
    observer.close()
    data=read_snapshot(observer.path)
    assert len(data['events'])<=200 and observer.path.stat().st_size<=LIMIT
    assert list(observer.folder.iterdir())==[observer.path]


def test_writer_failure_is_visible_and_never_raises_into_alice(tmp_path):
    observer=make(tmp_path)
    with patch('observation.os.replace',side_effect=PermissionError('private path')):
        observer.flush()
        assert observer.io_error=='PermissionError'
        assert not observer.path.with_suffix('.pending').exists()
    observer.flush()
    assert observer.io_error is None
    observer.close()


def test_waiting_confirmation_not_mistaken_for_stuck_generation(tmp_path):
    observer=make(tmp_path)
    with observer.span('memory_dialogue'),observer.span('confirmation'):
        data=observer.snapshot()
        for p in data['active']: p['seconds']=100
        assert 'slow_stage' not in [f['code'] for f in assess(data)]
        data['active']=data['active'][:1]
        assert 'slow_stage' in [f['code'] for f in assess(data)]
    observer.close()


def test_stale_is_unknown_not_crash_and_no_false_quality_verdict(tmp_path):
    observer=make(tmp_path)
    observer.ready()
    data=observer.snapshot()
    findings=assess(data,now=data['heartbeat']+30)
    assert any(f['code']=='stale' and 'inconnu' in f['text'] for f in findings)
    assert 'NON EVALUEE automatiquement' in format_snapshot(data)
    observer.close()


def test_error_timing_flag_and_playback_latency_are_observed(tmp_path):
    observer=make(tmp_path)
    observer.begin_turn('test','text')
    with pytest.raises(ValueError):
        with observer.span('model'): raise ValueError('private example')
    observer.emit('voice.playback_started')
    observer.emit('user.flag')
    observer.flush()
    data=read_snapshot(observer.path)
    assert not data['active']
    assert any(e['kind']=='phase.end' and e['metrics']['seconds']>=0 for e in data['events'])
    assert any(e['kind']=='voice.playback_started' and e['metrics']['seconds_since_input']>=0 for e in data['events'])
    assert {'reported_error','user_flag'}<={f['code'] for f in assess(data)}
    assert 'private example' not in observer.path.read_text(encoding='utf8')
    observer.close()


def test_voice_latency_includes_detection_and_transcription_without_reusing_it_for_text(tmp_path):
    observer=make(tmp_path)
    with patch('observation.time.monotonic',return_value=100):
        observer.begin_turn('validation audio','voice',speech_end_monotonic=98)
    with patch('observation.time.monotonic',return_value=103):
        observer.emit('voice.playback_started')
    metrics=observer.snapshot()['events'][-1]['metrics']
    assert metrics['seconds_since_input']==3
    assert metrics['seconds_since_vad_speech_end']==5
    observer.begin_turn('validation text','text')
    observer.emit('voice.playback_started')
    assert 'seconds_since_vad_speech_end' not in observer.snapshot()['events'][-1]['metrics']
    observer.close()


def test_actual_memory_forgetting_purges_diagnostic_sources(tmp_path):
    observer=make(tmp_path,True)
    session=Mock();session.observer=observer
    memory=Memory(session,'validation_observation',tmp_path/'validation_memory.db',Mock())
    try:
        event,_=memory.store.record_event(request_id='validation_forget_source',role='user',channel='text',content='PRIVATE_SOURCE')
        memory.store.remember(statement='PRIVATE_SOURCE',kind='confirmed',confidence=1,event_id=event.id,evidence_quote='PRIVATE_SOURCE',key='user.test')
        observer.emit('memory.written',detail={'text':'PRIVATE_SOURCE'})
        observer.flush()
        assert 'PRIVATE_SOURCE' in observer.path.read_text(encoding='utf8')
        reply,forgot=memory.forget(None,lambda _:True)
        observer.flush()
        assert forgot and 'PRIVATE_SOURCE' not in observer.path.read_text(encoding='utf8')
        assert memory.store.integrity()['events']==0
    finally: memory.close();observer.close()


def test_background_writer_cannot_restore_purged_content(tmp_path):
    observer=Observation(True,tmp_path/'validation_async',background=True)
    try:
        observer.emit('turn.reply',detail={'text':'DELETE_ME'})
        observer.flush()
        observer.purge()
        observer.flush()
        assert 'DELETE_ME' not in observer.path.read_text(encoding='utf8')
    finally: observer.close()
    assert not observer.thread.is_alive()


def test_real_profile_cannot_be_used_by_test():
    with pytest.raises(RuntimeError): Observation()


def test_model_metrics_never_capture_prompt_or_internal_reasoning(tmp_path):
    from chat import Session
    observer=make(tmp_path,True)
    session=Session.__new__(Session)
    session.model_spec={'family':'gemma4','expose_schema':True}
    import threading
    session.inference_lock=threading.RLock()
    session.observer=observer
    session.request=Mock(side_effect=[{'prompt':'PRIVATE_PROMPT'}, {'tokens':[1,2,3]},
        {'choices':[{'finish_reason':'stop','message':{'content':'Bonjour','reasoning_content':'PRIVATE_REASONING'}}],
         'usage':{'completion_tokens':2}}])
    assert session.ask([{'role':'user','content':'PRIVATE_PROMPT'}])[0]=='Bonjour'
    observer.close()
    raw=observer.path.read_text(encoding='utf8')
    assert 'PRIVATE_' not in raw
    assert 'model.input' in raw and 'model.output' in raw


def test_playback_hook_without_sound_and_file_is_cleaned(tmp_path):
    from voice_link import Voice
    observer=make(tmp_path)
    session=Mock();session.observer=observer
    voice=Voice(session)
    audio=tmp_path/'validation_audio.wav';audio.write_bytes(b'fixture')
    def parts(_text):
        try: yield audio,{'audio_seconds':0}
        finally: audio.unlink(missing_ok=True)
    voice.audio_parts=parts
    observer.begin_turn('test','text')
    with patch('winsound.PlaySound') as play:
        voice.speak('test')
        assert play.call_count==3
    observer.close()
    assert not audio.exists()
    kinds={e['kind'] for e in read_snapshot(observer.path)['events']}
    assert {'voice.playback_started','voice.playback_stopped'}<=kinds


def test_failed_trace_deletion_is_reported(tmp_path):
    observer=make(tmp_path,True)
    observer.emit('turn.reply',detail={'text':'PRIVATE_TEXT'})
    observer.flush()
    with patch('observation.os.replace',side_effect=PermissionError()), \
         patch.object(Path,'unlink',side_effect=PermissionError()):
        assert observer.purge() is False
        assert observer.io_error=='PermissionError'
    observer.close()
