"""Local desktop boundary for qualified native text actions; no eager PC access."""
from contextlib import nullcontext
from .native_text_request import interpret
from .native_text_dialogue import NativeTextDialogue


def desktop_guard(session):
    import psutil
    from chat import GAMES, processes
    session.check()
    if GAMES & processes():
        raise RuntimeError('native_game_active')
    if psutil.virtual_memory().available < 6 * 1024**3:
        raise RuntimeError('native_ram_low')


def backend_components(guard):
    from .native_window_catalog import WindowCatalog
    from .native_window_focus import NativeWindowFocus
    from .native_backend_factory import NativeBackendFactory
    from .native_typing_context import notepad_typing_context
    catalog = WindowCatalog(['notepad.exe'])
    factory = NativeBackendFactory(catalog, guard,
        focus=NativeWindowFocus(catalog, guard),
        typing_context_factory=notepad_typing_context)
    return catalog, factory


class DesktopNative:
    def __init__(self, session, *, components=backend_components, guard=desktop_guard):
        self.session, self.components, self.guard = session, components, guard
        self.controller = None
        self.epoch = 0

    def cancel(self):
        self.epoch += 1
        if self.controller is not None:
            self.controller.cancel()

    def can_handle(self, text, source):
        return interpret(text, source)['status'] != 'not_handled'

    def handle(self, text, source, *, cancelled=lambda: False):
        intent = interpret(text, source)  # Before imports, inventory or focus.
        if intent['status'] != 'ready':
            return {'status': intent['status'], 'verified': False,
                    'reply': intent.get('reply', 'Precise la fenetre et le texte exact a saisir.')}
        epoch = self.epoch
        def interrupted():
            return cancelled() or self.epoch != epoch
        def check():
            if interrupted():
                raise RuntimeError('native_request_interrupted')
            self.guard(self.session)
            if interrupted():
                raise RuntimeError('native_request_interrupted')
        try:
            check()
            catalog, factory = self.components(check)
            check()
            self.controller = NativeTextDialogue(self.session, catalog, factory,
                                                 allowed_processes=['notepad.exe'])
            return self.controller.handle(text, source, cancelled=interrupted)
        except Exception as error:
            from .native_text_dialogue import failure_reply
            return {'status': 'unverified', 'verified': False,
                    'reply': failure_reply(error)}
        finally:
            if self.controller is not None:
                self.controller.cancel()
            self.controller = None


def run_native_turn(app, text, source):
    epoch = app.speech_epoch
    listener_failed = None
    cancelled = lambda: (app.stop.is_set() or not app.inputs.empty()
                        or app.session.voice.interruption_epoch != epoch
                        or (listener_failed is not None and listener_failed()))
    # The ordinary listening turn has ended here. Reuse the opt-in stop-only
    # listener while acting, then release it before say() opens its own listener.
    listener = getattr(app.session.voice, 'stop_listener', None)
    try:
        with (listener() if listener is not None else nullcontext()) as listener_failed:
            result = app.natives.handle(text, source, cancelled=cancelled)
    finally:
        app.natives.cancel()
    app.observation.emit('native.result', {'status': result['status'],
                                          'verified': result.get('verified') is True})
    if not cancelled():
        app.say(result['reply'])
    return result
