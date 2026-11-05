"""Bounded silent Sopro requests while an existing recording is replayed."""
import threading
import time

TEXT = ('Une lumière traverse le verre, puis change de direction. '
        'On peut vérifier une idée sans transformer une supposition en certitude.')


class SilentSynthesis:
    def __init__(self, session):
        self.session = session
        self.stop = threading.Event()
        self.first = threading.Event()
        self.done = threading.Event()
        self.report = {'requests':0, 'packets':0, 'finished':False, 'error_type':None}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            deadline=time.monotonic()+30
            while not self.stop.is_set() and time.monotonic()<deadline:
                self.session.check()
                # Drain every request completely; packets are deleted by Voice.
                # Never play or retain the synthetic speech generated here.
                for _path, _info in self.session.voice.audio_parts(TEXT):
                    self.report['packets']+=1
                    self.first.set()
                self.report['requests']+=1
                if self.stop.wait(.01): break
            self.report['finished']=True
        except Exception as error:
            self.report['error_type']=type(error).__name__
        finally:
            self.done.set()

    def start(self):
        self.thread.start()
        deadline=time.monotonic()+30
        while not self.first.wait(.1):
            self.session.check()
            if self.done.is_set() or time.monotonic()>deadline:
                raise RuntimeError('Generation muette indisponible')

    def close(self):
        self.stop.set()
        deadline=time.monotonic()+30
        while self.thread.is_alive():
            self.thread.join(.1)
            self.session.check()
            if time.monotonic()>deadline:
                self.session.reason='Arret du diagnostic : generation muette non terminee'
                self.session.stop_owned()
                raise RuntimeError(self.session.reason)
