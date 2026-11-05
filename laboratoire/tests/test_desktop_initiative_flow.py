"""Exercise Application.run with synthetic services and no GUI/audio/network."""
from contextlib import ExitStack
from pathlib import Path
import queue
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alice_desktop


@pytest.fixture
def flow(monkeypatch):
    # Application.__init__ starts GUI threads. Test the actual run controller
    # directly, while all service construction and boundary effects remain fake.
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    app = alice_desktop.Application.__new__(alice_desktop.Application)
    app.stop = threading.Event()
    app.paused = threading.Event()
    app.stop_word_enabled = threading.Event()
    app.finished = threading.Event()
    app.inputs = queue.Queue()
    app.channel_commands = queue.Queue()
    app.events = queue.Queue()
    app.channels = None
    app.initiative = None
    app.observation = MagicMock()
    app.confirm = Mock(return_value=False)
    app.session = Mock(model_spec={'name': 'validation_initiative_flow'})
    app.session.voice = Mock()
    app.session.voice.speak.return_value = True
    app.hearing = Mock()
    services = Mock()
    services.start.return_value = True
    services.hearing = app.hearing
    services.memory = Mock()
    services.memory.answer.return_value = ('Reponse fictive.', False)
    services.library = Mock(available=False)
    services.public_memory = Mock()
    services.thoughts = Mock()
    services.close.side_effect = app.finished.set
    initiative = Mock()
    initiative.has_ready.return_value = False
    with ExitStack() as stack:
        factory = stack.enter_context(patch('alice_desktop.DesktopServices', return_value=services))
        stack.enter_context(patch('alice_desktop.DesktopInitiative', return_value=initiative))
        actions = stack.enter_context(patch('alice_desktop.Actions'))
        stack.enter_context(patch('alice_desktop.pc_tools'))
        router = stack.enter_context(patch('intent_router.route'))
        parser = stack.enter_context(patch('alice_desktop.parse', wraps=alice_desktop.parse))
        yield SimpleNamespace(app=app, services=services, initiative=initiative,
                              actions=actions.return_value, router=router, parser=parser,
                              factory=factory)


def test_mode_commands_bypass_actions_and_memory(flow):
    for text in ('/initiative animation', '/initiative discussion', '/initiative calme', 'quitte'):
        flow.app.inputs.put(text)
    flow.app.run()
    assert [call.args[0] for call in flow.initiative.set_mode.call_args_list] == [
        'animation', 'discussion', 'quiet']
    flow.parser.assert_called_once_with('quitte')
    flow.router.assert_not_called()
    flow.services.memory.answer.assert_not_called()
    flow.actions.execute.assert_not_called()
    flow.app.session.voice.speak.assert_not_called()
    flow.initiative.close.assert_called_once()
    flow.services.close.assert_called_once()
    assert flow.app.finished.is_set()


def test_ready_initiative_yields_silent_hearing_then_delivers(flow):
    def hear(operation, **kwargs):
        assert operation == 'listen'
        assert not kwargs['cancel_if']()
        assert not kwargs['yield_if']()
        flow.initiative.has_ready.return_value = True
        assert kwargs['yield_if']()
        assert not kwargs['cancel_if']()
        return {'status': 'idle'}
    def deliver(say, history, cancelled):
        assert not cancelled()
        say('Une intervention fictive.')
        flow.app.stop.set()
        return True
    flow.app.hearing.command.side_effect = hear
    flow.initiative.deliver.side_effect = deliver
    flow.app.run()
    flow.app.hearing.command.assert_called_once()
    flow.initiative.deliver.assert_called_once()
    flow.app.session.voice.speak.assert_called_once_with('Une intervention fictive.')
    flow.services.memory.answer.assert_not_called()
    flow.actions.execute.assert_not_called()
    flow.services.close.assert_called_once()


def test_pending_local_input_has_priority_over_ready_initiative(flow):
    flow.initiative.has_ready.return_value = True
    flow.app.inputs.put('/initiative calme')
    flow.app.inputs.put('quitte')
    flow.app.run()
    flow.initiative.set_mode.assert_called_once_with('quiet')
    flow.initiative.deliver.assert_not_called()
    flow.app.hearing.command.assert_not_called()
    flow.services.memory.answer.assert_not_called()


def test_local_input_arriving_during_listen_cancels_without_accepting_stale_audio(flow):
    def hear(operation, **kwargs):
        assert operation == 'listen'
        flow.app.inputs.put('/initiative calme')
        flow.app.inputs.put('quitte')
        assert kwargs['cancel_if']()
        return {'status': 'transcribed', 'accepted': True, 'cleaned': 'STALE_AUDIO'}
    flow.app.hearing.command.side_effect = hear
    flow.app.run()
    flow.initiative.set_mode.assert_called_once_with('quiet')
    assert 'STALE_AUDIO' not in repr(flow.parser.call_args_list)
    flow.services.memory.answer.assert_not_called()


def test_selected_public_turn_has_priority_over_ready_initiative(flow):
    from action_policy import Action
    channels = Mock()
    channels.pending = queue.Queue()
    channels.handle_one.side_effect = lambda *_: (flow.app.inputs.put('quitte') or True)
    flow.app.channels = channels
    flow.initiative.has_ready.return_value = True
    def parse_quit(text):
        # Check before the next turn's finally block can call idle again.
        assert text == 'quitte'
        flow.initiative.idle.assert_called_once_with([], channels)
        return Action('quit')
    flow.parser.side_effect = parse_quit
    flow.app.run()
    channels.handle_one.assert_called_once()
    flow.initiative.deliver.assert_not_called()
    flow.initiative.idle.assert_any_call([], channels)
    flow.services.memory.answer.assert_not_called()


def test_service_cleanup_survives_initiative_cleanup_exception(flow):
    flow.app.inputs.put('quitte')
    flow.initiative.close.side_effect = RuntimeError('validation_cleanup_failure')
    with pytest.raises(RuntimeError, match='validation_cleanup_failure'):
        flow.app.run()
    flow.services.close.assert_called_once()
    assert flow.app.finished.is_set()


def test_initialization_failure_still_closes_services(flow):
    flow.services.start.side_effect = RuntimeError('validation_start_failure')
    flow.app.run()
    flow.initiative.close.assert_not_called()
    flow.services.close.assert_called_once()
    flow.services.memory.answer.assert_not_called()


def test_channel_toggle_resumes_initiative_with_new_public_boundary(flow):
    from action_policy import Action
    channels = Mock()
    channels.pending = queue.Queue()
    flow.app.channels = channels
    flow.app.channel_commands.put('twitch')
    flow.app.inputs.put('quitte')
    def parse_quit(text):
        assert text == 'quitte'
        flow.initiative.idle.assert_called_once_with([], channels)
        return Action('quit')
    flow.parser.side_effect = parse_quit
    flow.app.run()
    channels.toggle.assert_called_once_with('twitch')
    flow.initiative.idle.assert_any_call([], channels)
    flow.services.close.assert_called_once()
def test_stop_during_generation_discards_reply_before_voice_delivery():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alice_desktop import Application
    voice = SimpleNamespace(interruption_epoch=2, speak=Mock())
    app = SimpleNamespace(session=SimpleNamespace(voice=voice), speech_epoch=1)
    assert Application.say(app, 'Reponse devenue perimee') is False
    voice.speak.assert_not_called()
