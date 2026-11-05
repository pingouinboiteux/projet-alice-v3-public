"""Own the desktop service lifecycle independently of dialogue and Tk widgets.

Factories are supplied by the entry point so importing this module never opens
a memory, starts a worker or connects a channel. Voice remains owned by Session.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ServiceFactories:
    session: Callable
    memory: Callable
    voice: Callable
    hearing: Callable
    library: Callable
    public_memory: Callable
    subtitles: Callable
    thoughts: Callable


class DesktopServices:
    def __init__(self, app, root: Path, factories: ServiceFactories):
        self.app = app
        self.root = root
        self.factories = factories
        self.session = self.memory = self.hearing = None
        self.library = self.public_memory = self.subtitles = self.thoughts = None
        self.started = False
        self.closed = False
        self.close_errors = []

    def start(self, *, startup=False):
        """Acquire services in their established order; return False on startup cancellation.

        The caller must close this owner in a finally block, including when a
        constructor or start method raises. Each completed acquisition is kept
        immediately so partial startup can release all previously owned objects.
        """
        if self.started or self.closed:
            raise RuntimeError('Cycle des services deja utilise')
        self.started = True
        app, factories = self.app, self.factories
        self.session = app.session = factories.session(
            allow_game=True, context_window=16384,
            fps_protection=False, ram_protection=False)
        self.session.observer = app.observation
        if startup:
            app.events.put(('status', 'Demarrage dans 30 secondes. Tu peux arreter Alice avec le bouton.'))
            if app.stop.wait(30):
                return False
        model_name = self.session.model_spec.get('name', 'modele local')
        app.events.put(('status', 'Chargement de '+model_name+'. Arrets automatiques FPS et RAM desactives a ta demande; surveillance active.'))
        with app.observation.span('startup_model'):
            self.session.start()
        self.session.check()
        app.events.put(('status', 'Chargement de la memoire locale sur CPU. Microphone ferme.'))
        with app.observation.span('startup_memory'):
            self.memory = factories.memory(self.session)
        self.session.check()
        app.events.put(('status', 'Chargement de la voix. Microphone ferme.'))
        self.session.voice = factories.voice(self.session)
        with app.observation.span('startup_voice'):
            self.session.voice.start()
        app.events.put(('text', ('Configuration vocale', self.session.voice.status_text())))
        self.session.check()
        app.events.put(('status', 'Chargement de l ecoute originale. Microphone ferme.'))
        self.hearing = app.hearing = factories.hearing(self.session)
        with app.observation.span('startup_hearing'):
            self.hearing.start()
        self.library = self.session.library = factories.library(self.session)
        ready = self.library.start()
        app.events.put(('text', ('Bibliotheque locale', 'Disponible hors ligne.' if ready else 'Indisponible : Alice continue sans documents.')))
        self.public_memory = factories.public_memory(
            self.root/'data/public/public_channels.db', 'public_channels', allow_public=True)
        self.subtitles = factories.subtitles(
            self.root/'sous_titre.txt', lambda: app.observation.emit('subtitles.write_error'))
        self.session.voice.subtitles = self.subtitles
        self.thoughts = self.session.thoughts = factories.thoughts(self.session)
        self.thoughts.start()
        app.observation.ready()
        return True

    def _close_step(self, phase, callback, *, event=None, visible=True):
        try:
            callback()
        except Exception as error:
            self.close_errors.append((phase, type(error).__name__))
            # Diagnostics must not prevent the remaining services from closing.
            if event:
                try:
                    if event == 'session.error':
                        self.app.observation.emit(event,
                            {'error_type': type(error).__name__, 'phase': phase},
                            {'message': str(error)})
                    else:
                        self.app.observation.emit(event)
                except Exception:
                    pass
            if visible:
                self.app.events.put(('text', ('Nettoyage', str(error))))

    def close(self):
        """Attempt every cleanup once, even after partial startup or close errors."""
        if self.closed:
            return
        self.closed = True
        if self.thoughts is not None:
            self._close_step('thoughts_close', self.thoughts.close, event='session.error')
        for name, service in (('subtitles', self.subtitles), ('library', self.library),
                              ('public_memory', self.public_memory)):
            if service is not None:
                callback = service.clear if name == 'subtitles' else service.close
                self._close_step(name+'_close', callback, event='social.close_error', visible=False)
        # Channels can be acquired later by the dialogue loop, after start().
        channels = self.app.channels
        if channels is not None:
            self._close_step('channels_close', channels.close, event='external.close_error', visible=False)
        if self.memory is not None:
            self._close_step('memory_close', self.memory.close, event='session.error')
        if self.hearing is not None:
            self._close_step('hearing_close', self.hearing.close)
        if self.session is not None:
            # Session owns the voice, worker processes, guards and temporary files.
            self._close_step('session_close', self.session.close)
        if self.thoughts is not None:
            self._close_step('thoughts_join', self.thoughts.join, event='session.error')
        self.app.finished.set()
        self.app.events.put(('finished', None))
        self._close_step('observation_close', self.app.observation.close)
