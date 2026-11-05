"""Private microphone/transcription worker reusing Alice's original hearing stack."""
import contextlib
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['ALICE_ROOT'] = str(ROOT)
os.environ['ALICE_USER'] = 'validation_lab_hearing'
os.environ['ALICE_HEARING_DML'] = '0'  # Same CPU backend as current Alice; never use the game GPU.
os.environ['HF_HUB_OFFLINE'] = '1'
sys.path.insert(0, str(ROOT / 'src'))


def send(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    from private_output_path import private_output_path
    folder = private_output_path(ROOT, sys.argv[1])
    os.environ['ALICE_LOG_DIRECTORY'] = str(folder)
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        from alice.hearing.service import load_model, decode_wav
        from alice.hearing.capture import SpeechCapture, WakeWindow
        from alice.hearing.turn import TurnDetector
        from alice.settings import load_settings
        from openwakeword.vad import VAD
        settings = load_settings()
        config = settings.section('conversation')
        started = time.monotonic()
        model = load_model()
        turn = TurnDetector()
        vad = VAD(model_path=str(settings.path('vad')), n_threads=1)
    wake = WakeWindow('Alice', config['conversation_window_seconds'], config['wake_name_aliases'])
    remote_wake = WakeWindow('Alice', config['conversation_window_seconds'], config['wake_name_aliases'])
    def make_capture():
        return SpeechCapture(**{k: config[k] for k in (
            'sample_rate', 'frame_samples', 'minimum_speech_seconds',
            'short_silence_seconds', 'fixed_silence_seconds',
            'maximum_silence_seconds', 'turn_confidence')}, turn_probability=turn.probability)
    def make_stop_capture():
        return SpeechCapture(minimum_speech_seconds=.15,
            short_silence_seconds=.3, fixed_silence_seconds=.4,
            maximum_silence_seconds=.6, maximum_utterance_seconds=3)
    def microphone():
        import sounddevice as sd
        devices = list(sd.query_devices())
        preferred = [s.casefold() for s in config['preferred_micro_names']]
        device = next((i for i, d in enumerate(devices)
            if d['max_input_channels'] > 0 and any(s in d['name'].casefold() for s in preferred)),
            int(sd.default.device[0]))
        if device < 0:
            raise RuntimeError('Aucun microphone disponible')
        sd.check_input_settings(device=device, channels=1, dtype='int16', samplerate=16000)
        return device, devices[device]['name']
    commands = queue.Queue()
    cancelled = threading.Event()
    yield_requested = threading.Event()

    def incoming():
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('op') == 'cancel':
                cancelled.set()
            elif request.get('op') == 'yield_if_idle':
                yield_requested.set()
            else:
                if request.get('op') in {'listen', 'stop_only'}:
                    cancelled.clear()
                    yield_requested.clear()
                commands.put(request)
        cancelled.set()
        commands.put({'op': 'quit'})

    threading.Thread(target=incoming, daemon=True).start()
    send({'status': 'ready', 'backend': 'CPUExecutionProvider',
          'load_seconds': round(time.monotonic() - started, 3)})
    while True:
        request = commands.get()
        if request['op'] == 'quit':
            return
        started = time.monotonic()
        identifier = request['id']
        try:
            op = request['op']
            audio = None
            capture_reason = None
            speech_end_monotonic = None
            if op == 'device':
                index, name = microphone()
                send({'id': identifier, 'status': 'device_checked', 'index': index,
                      'name': name, 'microphone_opened': False})
                continue
            elif op == 'remote_audio':
                from remote_audio import voiced_audio
                # Reuse Silero without changing the local microphone wake window.
                audio=voiced_audio(request['pcm'],vad)
                if audio is None:
                    send({'id':identifier,'status':'idle'}); continue
            elif op in {'transcribe', 'transcribe_stop'}:
                path = (ROOT / request['file']).resolve()
                if not path.is_relative_to(folder):
                    raise ValueError('Audio hors session privee')
                audio = decode_wav(path.read_bytes())
                if request.get('validate_capture'):
                    capture = make_stop_capture() if op == 'transcribe_stop' else make_capture()
                    padded = np.concatenate([audio, np.zeros(16000 * 4, dtype=np.float32)])
                    captured = None
                    for start in range(0, len(padded) - 480, 480):
                        frame = padded[start:start+480]
                        speaking = vad.predict((frame * 32767).astype(np.int16), frame_size=480) > config['speech_threshold']
                        captured = capture.feed(frame, speaking)
                        if captured is not None:
                            break
                    if captured is None:
                        raise RuntimeError('La detection ne trouve pas de tour de parole')
                    audio = captured.audio
                    capture_reason = captured.end_reason
            elif op == 'extend':
                wake.extend(time.monotonic())
                send({'id': identifier, 'status': 'extended'})
                continue
            elif op in {'listen', 'stop_only'}:
                import sounddevice as sd
                capture = make_stop_capture() if op == 'stop_only' else make_capture()
                device, _ = microphone()
                with sd.InputStream(samplerate=16000, channels=1, dtype='int16',
                        blocksize=480, device=device) as stream:
                    from hearing_capture_loop import capture_input
                    audio,capture_reason,speech_end_monotonic=capture_input(stream,capture,vad,np,
                        config['speech_threshold'],cancelled,yield_requested,started,
                        restart_capture=make_stop_capture if op == 'stop_only' else None)
                if cancelled.is_set() or audio is None:
                    send({'id': identifier, 'status': 'idle'})
                    continue
            else:
                raise ValueError('Commande inconnue')
            transcription_started=time.monotonic()
            with contextlib.redirect_stdout(sys.stderr):
                text = model.recognize(audio, sample_rate=16000, language='fr', target_language='fr').strip()
            if op in {'stop_only', 'transcribe_stop'}:
                from stop_command import is_stop_command
                send({'id': identifier, 'status': 'stop' if (op == 'transcribe_stop' or not cancelled.is_set())
                      and is_stop_command(text) else 'ignored',
                      'capture_reason':capture_reason, 'audio_seconds':round(len(audio)/16000,3)})
                continue
            decision = (remote_wake if op == 'remote_audio' else wake).decide(text, time.monotonic())
            send({'id': identifier, 'status': 'transcribed', 'text': text,
                  'accepted': decision.accepted, 'cleaned': decision.cleaned,
                  'wake_reason': decision.reason, 'capture_reason': capture_reason,
                  'transcription_seconds': round(time.monotonic()-transcription_started,3),
                  'audio_seconds': round(len(audio)/16000,3),
                  'audio_peak': round(float(np.max(np.abs(audio))),4),
                  'speech_end_monotonic':speech_end_monotonic,
                  'turn_detection_seconds':round(transcription_started-speech_end_monotonic,3) if speech_end_monotonic is not None else None,
                  'seconds': round(time.monotonic()-started, 3)})
        except Exception as error:
            send({'id': identifier, 'status': 'error', 'error': str(error),
                  'error_type':type(error).__name__,
                  'error_code':'input_overflow' if ('Capture micro incomplete' in str(error)
                      or 'debordements micro repetes' in str(error)) else 'worker_failed'})


if __name__ == '__main__':
    main()
