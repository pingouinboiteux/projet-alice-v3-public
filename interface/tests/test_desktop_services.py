"""Lifecycle contracts with fake services: no model, memory, microphone or network."""
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from desktop_services import DesktopServices, ServiceFactories


NAMES = ('session', 'memory', 'voice', 'hearing', 'library', 'public_memory',
         'subtitles', 'thoughts')


def world(root, fail=None, close_failures=()):
    trace, objects = [], {}

    def record(name):
        trace.append(name)
        if name == fail or name in close_failures:
            raise RuntimeError('validation failure: '+name)

    class Service:
        def __init__(self, name):
            self.name = name
            self.voice = None
            self.model_spec = {'name': 'Validation model'}
            self.available = False

        def start(self):
            record(self.name+'.start')
            return False  # A missing optional library must not stop startup.

        def check(self):
            record(self.name+'.check')

        def status_text(self):
            record(self.name+'.status_text')
            return 'Validation voice'

        def close(self):
            record(self.name+'.close')
            if self.name == 'session' and self.voice:
                self.voice.close()

        def clear(self):
            record(self.name+'.clear')

        def join(self):
            record(self.name+'.join')

        def active(self):
            record(self.name+'.active')

        def idle(self, messages):
            record(self.name+'.idle')

    def factory(name):
        def create(*args, **kwargs):
            record(name+'.create')
            service = objects[name] = Service(name)
            return service
        return Mock(side_effect=create)

    @contextmanager
    def span(name):
        trace.append('span.'+name)
        yield

    observation = SimpleNamespace(span=span,
        emit=lambda *args, **kwargs: trace.append('observe.'+args[0]),
        ready=lambda: record('observation.ready'),
        close=lambda: record('observation.close'), begin_turn=lambda *a, **k: None)
    app = SimpleNamespace(events=Queue(), stop=Event(), finished=Event(),
        observation=observation, session=None, hearing=None, channels=None,
        paused=Event(), inputs=Queue(), channel_commands=Queue(), confirm=Mock())
    factories = ServiceFactories(**{name: factory(name) for name in NAMES})
    owner = DesktopServices(app, root, factories)
    return owner, app, factories, objects, trace


def assert_closed(owner, app, objects, trace):
    for name in objects:
        method = 'clear' if name == 'subtitles' else 'close'
        assert name+'.'+method in trace
    assert app.finished.is_set()
    assert list(app.events.queue).count(('finished', None)) == 1
    assert trace[-1] == 'observation.close'


def test_start_order_configuration_and_shutdown_ownership(tmp_path):
    owner, app, factories, objects, trace = world(tmp_path)
    assert owner.start()
    assert [item for item in trace if item.endswith(('.create', '.start'))] == [
        'session.create', 'session.start', 'memory.create', 'voice.create',
        'voice.start', 'hearing.create', 'hearing.start', 'library.create',
        'library.start', 'public_memory.create', 'subtitles.create',
        'thoughts.create', 'thoughts.start']
    factories.session.assert_called_once_with(allow_game=True, context_window=16384,
        fps_protection=False, ram_protection=False)
    factories.public_memory.assert_called_once_with(
        tmp_path/'data/public/public_channels.db', 'public_channels', allow_public=True)
    assert app.session is owner.session
    assert app.hearing is owner.hearing
    assert owner.session.voice.subtitles is owner.subtitles
    assert owner.session.library is owner.library
    assert owner.session.thoughts is owner.thoughts
    assert any('Indisponible' in str(event) for event in app.events.queue)
    app.channels = SimpleNamespace(close=lambda: trace.append('channels.close'))
    trace.clear()
    owner.close()
    assert trace == ['thoughts.close', 'subtitles.clear', 'library.close',
        'public_memory.close', 'channels.close', 'memory.close', 'hearing.close',
        'session.close', 'voice.close', 'thoughts.join', 'observation.close']
    assert_closed(owner, app, objects, trace)
    owner.close()
    assert trace.count('voice.close') == 1
    assert list(app.events.queue).count(('finished', None)) == 1
    with pytest.raises(RuntimeError): owner.start()


@pytest.mark.parametrize('failure', [
    'session.create', 'session.start', 'session.check', 'memory.create',
    'voice.create', 'voice.start', 'voice.status_text', 'hearing.create',
    'hearing.start', 'library.create', 'library.start', 'public_memory.create',
    'subtitles.create', 'thoughts.create', 'thoughts.start', 'observation.ready',
])
def test_failed_acquisition_closes_every_previously_acquired_service(tmp_path, failure):
    owner, app, factories, objects, trace = world(tmp_path, fail=failure)
    with pytest.raises(RuntimeError, match='validation failure'):
        try:
            owner.start()
        finally:
            owner.close()
    assert_closed(owner, app, objects, trace)
    assert list(app.events.queue).count(('finished', None)) == 1


def test_cancelled_delayed_start_does_not_acquire_memory_or_workers(tmp_path):
    owner, app, factories, objects, trace = world(tmp_path)
    app.stop.set()
    try:
        assert not owner.start(startup=True)
    finally:
        owner.close()
    assert set(objects) == {'session'}
    assert 'session.start' not in trace
    for name in NAMES[1:]: getattr(factories, name).assert_not_called()
    assert_closed(owner, app, objects, trace)


@pytest.mark.parametrize('failure', ['thoughts.close', 'subtitles.clear', 'library.close',
    'public_memory.close', 'memory.close', 'hearing.close', 'thoughts.join', 'observation.close'])
def test_close_error_does_not_skip_other_services_or_finished(tmp_path, failure):
    owner, app, factories, objects, trace = world(tmp_path, close_failures=(failure,))
    owner.start()
    owner.close()
    assert_closed(owner, app, objects, trace)
    assert owner.close_errors


def test_multiple_shutdown_errors_and_broken_diagnostics_still_finish(tmp_path):
    owner, app, factories, objects, trace = world(tmp_path,
        close_failures=('thoughts.close', 'memory.close', 'session.close', 'thoughts.join'))
    owner.start()
    app.channels = SimpleNamespace(close=Mock(side_effect=RuntimeError('validation channel')))
    app.observation.emit = Mock(side_effect=OSError('validation log unavailable'))
    owner.close()
    app.channels.close.assert_called_once()
    assert 'hearing.close' in trace and 'session.close' in trace
    assert trace[-1] == 'observation.close'
    assert app.finished.is_set()
    assert len(owner.close_errors) == 5
    assert list(app.events.queue).count(('finished', None)) == 1


@pytest.mark.parametrize('failure', ['session.create', 'thoughts.close'])
def test_real_controller_finishes_when_creation_or_cleanup_fails(tmp_path, monkeypatch, failure):
    import alice_desktop
    owner, app, factories, objects, trace = world(tmp_path,
        fail=failure if failure.endswith('create') else None,
        close_failures=(failure,) if failure.endswith('close') else ())
    for name, symbol in zip(NAMES, ('Session', 'Memory', 'Voice', 'Hearing',
                                    'Library', 'PublicMemory', 'Subtitles', 'Thoughts')):
        monkeypatch.setattr(alice_desktop, symbol, getattr(factories, name))
    monkeypatch.setattr(alice_desktop, 'ROOT', tmp_path)
    monkeypatch.setattr(alice_desktop, 'Actions', Mock())
    monkeypatch.setattr(alice_desktop, 'pc_tools', SimpleNamespace(Monitor=Mock()))
    monkeypatch.setattr(alice_desktop, 'sys', SimpleNamespace(argv=['validation']))
    monkeypatch.chdir(tmp_path)
    app.inputs.put('quitte')
    app.say = Mock()
    alice_desktop.Application.run(app)
    assert_closed(owner, app, objects, trace)
