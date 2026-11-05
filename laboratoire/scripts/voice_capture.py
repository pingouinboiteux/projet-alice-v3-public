"""Explicitly authorized, one-shot, bounded recording of generated PCM only."""
import hashlib
import json
from pathlib import Path
import time
import threading
import wave

FOLDER = Path(__file__).resolve().parents[1]/'logs/observation'
MAX_BYTES = 24000*2*180
NAMES = ('voice_capture_armed.json', 'voice_capture.wav', 'voice_capture.json', 'voice_output_test.json')
_lock = threading.RLock()
_active = None


def purge(folder=FOLDER):
    global _active
    with _lock:
        if _active is not None and _active.folder.resolve() == folder.resolve():
            recording, _active = _active, None
            recording.closed = True
            recording.wav.close()
        for name in NAMES:
            (folder/name).unlink(missing_ok=True)


def arm(folder=FOLDER):
    folder.mkdir(parents=True, exist_ok=True)
    if any((folder/name).exists() for name in NAMES):
        raise RuntimeError('Un diagnostic vocal existe deja')
    (folder/NAMES[0]).write_text(json.dumps({'expires_at':time.time()+3600}), encoding='utf-8')


def begin(profile, folder=FOLDER):
    with _lock:
        return _begin(profile, folder)


def _begin(profile, folder):
    global _active
    marker = folder/NAMES[0]
    if not marker.exists(): return None
    try:
        request = json.loads(marker.read_text(encoding='utf-8'))
    finally:
        marker.unlink(missing_ok=True)
    if not time.time() < float(request['expires_at']) <= time.time()+3600:
        return None
    _active = Recording(folder, profile)
    return _active


class Recording:
    def __init__(self, folder, profile):
        self.folder = folder
        self.closed = False
        self.bytes = 0
        self.digest = hashlib.sha256()
        self.wav = wave.open(str(folder/NAMES[1]), 'wb')
        self.wav.setparams((1,2,24000,0,'NONE','not compressed'))
        self.report = {'profile':profile, 'microphone_recorded':False,
                       'complete':False, 'frames':0, 'packets':0,
                       'meaning':'Exact generated PCM before output; not a headset/loopback recording.'}
        self.save()

    def save(self):
        (self.folder/NAMES[2]).write_text(json.dumps(self.report, indent=2), encoding='utf-8')

    def append(self, path):
        with _lock:
            if self.closed: return
            self._append(path)

    def _append(self, path):
        with wave.open(str(path), 'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) != (1,2,24000):
                raise ValueError('Invalid captured PCM')
            raw = wav.readframes(wav.getnframes())
        if self.bytes+len(raw) > MAX_BYTES: raise ValueError('Voice capture limit exceeded')
        self.wav.writeframes(raw)
        self.bytes += len(raw)
        self.digest.update(raw)
        self.report.update(frames=self.bytes//2, pcm_sha256=self.digest.hexdigest(),
                           packets=self.report['packets']+1)
        self.save()

    def close(self, complete, underflows, output):
        global _active
        with _lock:
            if self.closed: return
            self.closed = True
            if _active is self: _active = None
            try: self.wav.close()
            finally:
                self.report.update(complete=complete, underflows=underflows, output=output)
                self.save()
