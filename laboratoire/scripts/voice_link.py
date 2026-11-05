"""Parent-side lifecycle, validation and playback for the private voice worker."""
import array
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import wave
from contextlib import nullcontext
from observation import emit, span

ROOT = Path(__file__).resolve().parents[1]


class VoiceRequestError(RuntimeError):
    def __init__(self,value):
        super().__init__(value['error'])
        self.request_id=value.get('id')


class SpeechInterrupted(Exception):
    """Only this utterance was stopped; the owning session remains alive."""


def inspect_wav(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise RuntimeError('Format audio inattendu')
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    if not 2400 <= frames <= 24000 * 180 or len(raw) != frames * 2:
        raise RuntimeError('Audio vide, tronque ou trop long')
    samples = array.array('h', raw)
    peak = max(abs(s) for s in samples)
    if peak < 100:
        raise RuntimeError('Audio silencieux')
    return {'audio_seconds': round(frames / 24000, 3), 'peak': peak, 'frames': frames}


class Voice:
    def __init__(self, session):
        self.session = session
        self.sequence = 0
        self.messages = queue.Queue()
        self.log = None
        self.process = None
        self.continuous_playback = False
        self.profile_name = None
        self.capture_allowed = False
        self.interrupted = threading.Event()
        self.interruption_epoch = 0
        self._delivery_poll = None
        self.stop_listener = None
        self.on_interrupt = None

    def interrupt(self):
        self.interruption_epoch += 1
        already_interrupted = self.interrupted.is_set()
        self.interrupted.set()
        if not already_interrupted and self.on_interrupt is not None:
            self.on_interrupt()

    def _check_speech(self):
        self.session.check()
        if self.interrupted.is_set():
            raise SpeechInterrupted()

    def start(self):
        from voice_profile import selected_voice
        profile=selected_voice()
        self.profile_name = profile['name']
        self.continuous_playback = profile['name'] == 'sopro_original'
        manifest = json.loads((ROOT / profile['manifest']).read_text())
        for relative, info in manifest['files'].items():
            path = ROOT / relative
            if not path.is_file() or path.stat().st_size != info['bytes']:
                raise RuntimeError('Ressource vocale absente ou modifiee : ' + relative)
        folder = Path(self.session.temp.name)
        self.log = (folder / 'voice.log').open('w', encoding='utf-8')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
                   PYTHONIOENCODING='utf-8', PYTHONPATH=str(ROOT / 'src'),
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
        env.pop('ALICE_GPU_PCI_BUS', None)
        self.process = subprocess.Popen(
            [str(ROOT / profile['python']), '-B',
             profile['worker'], folder.relative_to(ROOT).as_posix()], cwd=ROOT,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.session.children['voice'] = self.process
        self.session.job.assign(self.process)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.ready = self.receive(180)
        if self.ready.get('status') != 'ready':
            raise RuntimeError('Voix indisponible')
        emit(self.session, 'voice.ready', {'profile': self.profile_name,
            'continuous': self.continuous_playback,
            'sample_rate': self.ready.get('sample_rate'),
            'pci_bus': self.ready.get('pci_bus'), 'steps': self.ready.get('steps')})

    def status_text(self):
        if self.profile_name in {'sopro_original','sopro_d'}:
            steps=getattr(self,'ready',{}).get('steps')
            detail=f', {steps} etapes' if type(steps) is int else ''
            return "Voix chargee : Sopro, sample d'origine"+detail+", lecture continue."
        if self.profile_name == 'current':
            return 'Voix chargee : Chatterbox (ancienne voix).'
        return 'Voix non chargee.'

    def read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except Exception as error:
            self.messages.put({'status': 'error', 'error': str(error)})

    def receive(self, timeout, on_poll=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.session.check()
            if on_poll is not None:on_poll()
            if self.process.poll() is not None:
                raise RuntimeError('Le moteur vocal s est arrete')
            try:
                value = self.messages.get(timeout=.25)
            except queue.Empty:
                continue
            if value.get('status') == 'error':
                raise VoiceRequestError(value)
            return value
        raise RuntimeError('Delai vocal depasse')

    def synthesize(self, text):
        self.session.check()
        self.sequence += 1
        try:
            self.process.stdin.write(json.dumps({'id': self.sequence, 'text': text}, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
        except OSError:
            self.session.check()
            raise RuntimeError('La liaison avec la voix est fermee')
        with span(self.session,'voice_synthesis'):
            result = self.receive(180)
        if result.get('id') != self.sequence or result.get('status') != 'audio':
            raise RuntimeError('Reponse vocale incoherente')
        path = (ROOT / result['file']).resolve()
        if not path.is_relative_to(Path(self.session.temp.name).resolve()):
            raise RuntimeError('Chemin vocal hors session')
        result.update(inspect_wav(path))
        emit(self.session,'voice.audio', {k:result.get(k) for k in
            ('first_chunk_seconds','synthesis_seconds','audio_seconds','peak','chunks','frames')})
        return path, result

    def audio_parts(self,text):
        """One request, ordered complete files, explicit terminal record."""
        self.session.check()
        self.sequence+=1
        self.process.stdin.write(json.dumps({'id':self.sequence,'text':text,'stream':True},ensure_ascii=False)+'\n')
        self.process.stdin.flush()
        index=0
        total_frames=0
        expected_parts=None
        dynamic_parts=None
        deadline=time.monotonic()+360
        complete=False
        try:
            while True:
                # Errors are terminal for a request, as is audio_end.
                if time.monotonic()>=deadline: raise RuntimeError('Delai vocal depasse')
                try: result=self.receive(min(180,deadline-time.monotonic()), on_poll=self._delivery_poll)
                except VoiceRequestError as error:
                    complete=error.request_id==self.sequence
                    raise
                if result.get('id')!=self.sequence: raise RuntimeError('Sequence vocale incoherente')
                if result.get('status')=='audio_end':
                    if not index or type(result.get('parts')) is not int or result.get('parts')!=index or (expected_parts is not None and index!=expected_parts):
                        raise RuntimeError('Fin vocale incoherente')
                    complete=True
                    emit(self.session,'voice.stream_complete',{'parts':index,'seconds':result['synthesis_seconds']})
                    return
                if result.get('status')!='audio_part' or result.get('part')!=index:
                    raise RuntimeError('Ordre vocal incoherent')
                count=result.get('parts')
                dynamic=count is None
                if 'parts' not in result or (dynamic_parts is not None and dynamic!=dynamic_parts):
                    raise RuntimeError('Nombre de blocs incoherent')
                if not dynamic and (type(count) is not int or not index<count<=128 or (expected_parts is not None and count!=expected_parts)):
                    raise RuntimeError('Nombre de blocs incoherent')
                if index>=128:raise RuntimeError('Trop de blocs vocaux')
                dynamic_parts=dynamic
                expected_parts=count
                path=(ROOT/result['file']).resolve()
                if not path.is_relative_to(Path(self.session.temp.name).resolve()):
                    raise RuntimeError('Chemin vocal hors session')
                result.update(inspect_wav(path))
                total_frames+=result['frames']
                if total_frames>24000*180: raise RuntimeError('Reponse vocale trop longue')
                emit(self.session,'voice.audio',{k:result.get(k) for k in
                    ('first_chunk_seconds','synthesis_seconds','audio_seconds','peak','chunks','frames','part','parts')})
                index+=1
                try: yield path,result
                finally: path.unlink(missing_ok=True)
        finally:
            if not complete and self.process.poll() is None:
                # A consumer/protocol failure must not leak old parts into the
                # next turn. Stop this worker rather than reusing a broken pipe.
                self.process.terminate()
                self.process.wait(timeout=10)
            for path in Path(self.session.temp.name).glob(f'validation_voice_{self.sequence}_*.wav'):
                path.unlink(missing_ok=True)

    def speak(self, text):
        self.interrupted.clear()
        context = self.stop_listener() if self.stop_listener is not None else nullcontext()
        with context:
            return self._speak(text)

    def _speak(self, text):
        if self.continuous_playback:
            return self.speak_continuous(text)
        import winsound
        parts=self.audio_parts(text)
        subtitle=getattr(self,"subtitles",None);ticket=None
        try:
            for index,(path,result) in enumerate(parts):
                if self.interrupted.is_set():
                    continue  # Drain the request, without ever playing stale audio.
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                if index==0 and subtitle: ticket=subtitle.show(text)
                emit(self.session,'voice.playback_started' if index==0 else 'voice.part_playback_started',{'part':index})
                deadline=time.monotonic()+result['audio_seconds']+.03
                while time.monotonic()<deadline:
                    self.session.check()
                    if self.interrupted.is_set():
                        break
                    time.sleep(.01)
                winsound.PlaySound(None,0)
        finally:
            winsound.PlaySound(None,0)
            try: parts.close()
            finally:
                if subtitle and ticket is not None: subtitle.clear(ticket)
            emit(self.session,'voice.playback_stopped')
        return not self.interrupted.is_set()

    def speak_continuous(self, text):
        from continuous_playback import ContinuousPCM
        player = ContinuousPCM(self._check_speech)
        player_closed = False
        def poll_delivery():
            nonlocal player_closed
            if self.interrupted.is_set() and not player_closed:
                player.close(complete=False)
                player_closed = True
        self._delivery_poll = poll_delivery
        parts = self.audio_parts(text)
        subtitle = getattr(self, 'subtitles', None)
        ticket = None
        complete = False
        capture = None
        if self.capture_allowed:
            try:
                from voice_capture import begin
                capture = begin(self.profile_name)
                if capture is not None:
                    ready = getattr(self, 'ready', {})
                    capture.report['worker'] = {key:ready.get(key) for key in
                        ('backend','backend_version','sample_rate','device','pci_bus','steps',
                         'reference_sha256','prompt_noise_sha256')}
            except (OSError, ValueError, KeyError) as error:
                emit(self.session, 'voice.capture_error', {'error_type':type(error).__name__})
        try:
            for index, (path, result) in enumerate(parts):
                poll_delivery()
                if self.interrupted.is_set():
                    continue
                if capture is not None:
                    try: capture.append(path)
                    except (OSError, ValueError) as error:
                        emit(self.session, 'voice.capture_error', {'error_type':type(error).__name__})
                        try: capture.close(False, player.underflows, player.output_info)
                        except OSError: pass
                        capture = None
                if index == 0:
                    if subtitle:
                        ticket = subtitle.show(text)
                    # Submission time, not a measured physical speaker onset.
                    emit(self.session, 'voice.playback_submitted', {'part': index})
                try:
                    player.write(path)
                except SpeechInterrupted:
                    poll_delivery()
            complete = not self.interrupted.is_set()
        finally:
            self._delivery_poll = None
            try:
                if not player_closed:
                    player.close(complete=complete)
            finally:
                try:
                    parts.close()
                finally:
                    if capture is not None:
                        try: capture.close(complete, player.underflows, player.output_info)
                        except OSError as error:
                            emit(self.session, 'voice.capture_error', {'error_type':type(error).__name__})
                    if subtitle and ticket is not None:
                        subtitle.clear(ticket)
                    emit(self.session, 'voice.playback_stopped',
                         {'underflows': player.underflows, 'continuous': True})
        return complete

    def close(self):
        try:
            if self.process:
                if self.process.poll() is None:
                    self.process.terminate()
                self.process.wait(timeout=10)
                if hasattr(self, 'reader'):
                    self.reader.join(timeout=3)
                for pipe in (self.process.stdin, self.process.stdout):
                    if pipe:
                        try:
                            pipe.close()
                        except OSError:
                            # A killed worker can leave buffered input that cannot be flushed.
                            # It has already exited; always close the diagnostic handle below.
                            pass
        finally:
            if self.log:
                self.log.close()
