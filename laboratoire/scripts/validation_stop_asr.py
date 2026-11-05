"""Six synthetic TTS -> ASR stop checks; never opens a mic or audio output."""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
import wave
import audioop

from chat import ROOT, Session, Job, processes
from hearing_link import Hearing
from voice_link import Voice


CASES = (
    ('isolated', 'Stop.', 'stop'),
    ('addressed', 'Alice, stop.', 'stop'),
    ('grumbling', 'Mince, encore perdu.', 'ignored'),
    ('negated', 'Ne dis pas stop.', 'ignored'),
    ('emphatic', 'Stop !', 'stop'),
    ('ordinary', 'Je regarde tranquillement la partie.', 'ignored'),
)


def hearing_wav(source):
    """ASR decoder requires mono PCM16/16 kHz; Sopro emits 24 kHz."""
    target = source.with_name(source.stem+'_asr.wav')
    with wave.open(str(source), 'rb') as wav:
        if wav.getnchannels()!=1 or wav.getsampwidth()!=2:
            raise ValueError('Expected mono PCM16 source')
        pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1,
                              wav.getframerate(), 16000, None)
    with wave.open(str(target), 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return target


def run_cases(voice, hearing, record, root=ROOT):
    for name, text, expected in CASES:
        started = time.monotonic()
        path, audio = voice.synthesize(text)
        synthesis_seconds = time.monotonic() - started
        asr_path = None
        try:
            asr_path = hearing_wav(path)
            started = time.monotonic()
            result = hearing.command('transcribe_stop', file=asr_path.relative_to(root).as_posix())
            asr_seconds = time.monotonic() - started
            if result.get('status') not in {'stop', 'ignored'}:
                raise RuntimeError('Invalid stop-ASR response')
            record({'case':name, 'synthetic_text':text, 'expected':expected,
                    'status':result['status'], 'passed':result['status']==expected,
                    'synthesis_seconds':round(synthesis_seconds, 3),
                    'asr_command_seconds':round(asr_seconds, 3),
                    'audio_seconds':audio['audio_seconds']})
        finally:
            path.unlink(missing_ok=True)
            if asr_path is not None:
                asr_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-game-no-fps', action='store_true', required=True)
    args = parser.parse_args()
    folder = ROOT/'data/validation/validation_stop_20261105'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'asr_synthetic.json'
    if target.exists():
        raise RuntimeError('Previous report preserved; do not overwrite')
    if 'llama-server.exe' in processes():
        raise RuntimeError('Another model session is running; wait before this test')
    session = Session(allow_game=True, fps_protection=False)
    if session.minimum_ram < 6*2**30:
        raise RuntimeError('Six GiB free RAM required')
    report = {'status':'running', 'rows':[], 'microphone_opened':False,
        'audio_played':False, 'private_memory_opened':False,
        'ram_guard_gib':6, 'fps_exception_user_authorized':args.allow_game_no_fps,
        'scope':'Synthetic Sopro audio through installed ASR; no microphone, echo, noise or VAD qualification.'}
    def save():
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def record(row):
        report['rows'].append(row)
        save()
        print(json.dumps(row, ensure_ascii=False), flush=True)
    voice = Voice(session)
    hearing = Hearing(session)
    session.temp = tempfile.TemporaryDirectory(prefix='validation_stop_', dir=ROOT/'logs')
    temporary_path = Path(session.temp.name)
    session.job = Job()
    try:
        session.thread = threading.Thread(target=session.watch, daemon=True)
        session.thread.start()
        voice.start()
        hearing.start()
        report['voice_profile'] = voice.profile_name
        report['voice_steps'] = voice.ready.get('steps')
        report['hearing_backend'] = hearing.ready.get('backend')
        run_cases(voice, hearing, record)
        report['status'] = 'complete'
        report['passed'] = sum(row['passed'] for row in report['rows'])
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        try:
            try:
                hearing.close()
            finally:
                voice.close()
        finally:
            session.close()
            report['minimum_ram_free_gib'] = round(session.minimum_ram/2**30, 3)
            report['owned_workers_stopped'] = all(p.poll() is not None for p in session.children.values())
            report['temporary_data_removed'] = not temporary_path.exists()
            save()


if __name__ == '__main__':
    main()
