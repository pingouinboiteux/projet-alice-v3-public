"""Owned, cancellable hearing process. No shared HTTP listener or real memory."""
import json
import os
from pathlib import Path
import subprocess
import threading
from contextlib import contextmanager
from voice_link import Voice, ROOT
from observation import emit, span


class Hearing(Voice):
    @contextmanager
    def stop_only(self, voice, *, enabled=False, cancel_if=None, on_status=None):
        """Own the idle hearing worker; yield a failure probe for action guards.

        Opt-in: acoustic echo cancellation is not implemented. Headphones and a
        real microphone trial are required before claiming reliable recognition.
        """
        if not enabled:
            yield
            return
        finished = threading.Event()
        failed = threading.Event()
        errors = []
        def status(value):
            emit(self.session, 'hearing.stop_state', {'status':value})
            if on_status is not None: on_status(value)
        def stopped():
            if cancel_if is not None and cancel_if():
                finished.set()  # A later toggle must not reopen this utterance.
            return finished.is_set()
        def watch():
            try:
                status('requested')
                while not stopped():
                    result = self.command('stop_only', cancel_if=stopped)
                    if stopped(): break
                    if result.get('status') not in {'idle', 'ignored', 'stop'}:
                        raise RuntimeError('Reponse ecoute stop invalide')
                    status(result.get('status', 'error'))
                    if result.get('status') == 'stop' and not stopped():
                        voice.interrupt()
                        return
            except Exception as error:
                errors.append(error)
                failed.set()  # Visible to action guards before error notification.
                status('error')
        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        try:
            yield failed.is_set
        finally:
            finished.set()
            self.cancel()
            thread.join(timeout=15)
            if thread.is_alive():
                # A pending reader must never consume the next normal command.
                # Leave this worker visibly stopped rather than reusing its pipe.
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    self.process.wait(timeout=10)
                thread.join(timeout=2)
                raise RuntimeError('Ecoute stop non terminee; ne pas reutiliser le micro')
            if errors:
                raise RuntimeError('Ecoute stop indisponible') from errors[0]

    def start(self):
        manifest = json.loads((ROOT / 'config/hearing.lock.json').read_text(encoding='utf-8'))
        for relative, info in manifest['files'].items():
            path = ROOT / relative
            if not path.is_file() or path.stat().st_size != info['bytes']:
                raise RuntimeError('Ressource d ecoute absente ou modifiee : ' + relative)
        folder = Path(self.session.temp.name)
        self.log = (folder / 'hearing.log').open('w', encoding='utf-8')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
                   PYTHONIOENCODING='utf-8', PYTHONPATH=str(ROOT / 'src'),
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
        self.process = subprocess.Popen([str(ROOT / '.venv_hearing/Scripts/python.exe'),
            '-B', 'scripts/hearing_worker.py', folder.relative_to(ROOT).as_posix()],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.session.children['hearing'] = self.process
        self.session.job.assign(self.process)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.ready = self.receive(180)
        if self.ready.get('status') != 'ready':
            raise RuntimeError('Ecoute indisponible')
        self.write_lock = threading.Lock()

    def command(self, op, cancel_if=None, yield_if=None, **kwargs):
        self.session.check()
        if self.process.poll() is not None:
            raise RuntimeError(f'Le moteur d ecoute est arrete (code {self.process.returncode})')
        with self.write_lock:
            if cancel_if is not None and cancel_if():
                return {'status': 'idle'}
            self.sequence += 1
            try:
                self.process.stdin.write(json.dumps({'id': self.sequence, 'op': op, **kwargs}) + '\n')
                self.process.stdin.flush()
            except OSError:
                self.session.check()
                raise RuntimeError('La liaison avec le moteur d ecoute est fermee')
        with span(self.session,'listening' if op=='listen' else 'hearing_'+op):
            cancelled=False
            yielded=False
            def poll_cancel():
                nonlocal cancelled,yielded
                if not cancelled and cancel_if is not None and cancel_if():
                    self.cancel()
                    cancelled=True
                elif not cancelled and not yielded and yield_if is not None and yield_if():
                    self.yield_idle()
                    yielded=True
            result = self.receive(180,on_poll=poll_cancel) if cancel_if is not None or yield_if is not None else self.receive(180)
        if result.get('id') != self.sequence:
            raise RuntimeError('Reponse de transcription incoherente')
        if op in {'stop_only', 'transcribe_stop'}:
            # Only status crosses this boundary, including diagnostic mode.
            emit(self.session, 'hearing.stop_result', {key:result.get(key) for key in
                ('status','error_type','error_code','capture_reason','audio_seconds')})
            return {'status':result.get('status')}
        emit(self.session,'hearing.result',{'source':'discord' if op=='remote_audio' else 'local',
            'status':result.get('status'),'accepted':result.get('accepted'),
            'seconds':result.get('seconds'),'wake_reason':result.get('wake_reason'),
            'capture_reason':result.get('capture_reason'),'transcription_seconds':result.get('transcription_seconds'),
            'turn_detection_seconds':result.get('turn_detection_seconds'),
            'audio_seconds':result.get('audio_seconds'),'audio_peak':result.get('audio_peak')},
            {'transcript':result.get('text'),'cleaned':result.get('cleaned')})
        return result

    def cancel(self):
        self.signal('cancel')

    def yield_idle(self):
        self.signal('yield_if_idle')

    def signal(self,op):
        if self.process and self.process.poll() is None and hasattr(self, 'write_lock'):
            with self.write_lock:
                try:
                    self.process.stdin.write(json.dumps({'op':op})+'\n')
                    self.process.stdin.flush()
                except OSError:
                    pass  # The owning session will report the worker/guard failure.
