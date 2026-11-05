"""Adapter boundary and delivery races using a fake completion and no services."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from conversation_initiative import Initiative
from desktop_initiative import DesktopInitiative, mode_command


PRIVATE = [{'role': 'user', 'content': 'validation_private_secret'}]
PUBLIC = [{'role': 'user', 'content': 'validation_public_chess'}]


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(Initiative, 'start', lambda self: None)
    session = SimpleNamespace(ask_background=Mock(return_value=(json.dumps({
        'choice': 'continue', 'reply': 'Un sacrifice peut etre plus fort qu une defense passive.'}), 0, {})))
    value = DesktopInitiative(session)
    clock = [0.]
    value.core.clock = lambda: clock[0]
    return value, session, clock


def ready(value, clock):
    clock[0] += 100
    value.core.tick()
    assert value.has_ready()


def channels(public=PUBLIC, enabled=True):
    return SimpleNamespace(enabled={'twitch': enabled}, public_history=lambda: list(public))


def test_animation_never_gets_private_local_history(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle(PRIVATE, channels())
    ready(value, clock)
    prompt = session.ask_background.call_args.args[0]
    assert 'validation_private_secret' not in repr(prompt)
    assert 'validation_public_chess' in repr(prompt)


def test_discussion_connected_public_has_public_context_only(adapter):
    value, session, clock = adapter
    value.set_mode('discussion'); value.idle(PRIVATE, channels())
    ready(value, clock)
    assert 'validation_private_secret' not in repr(session.ask_background.call_args)
    history = list(PRIVATE)
    assert value.deliver(lambda text: True, history, lambda: False)
    assert history == PRIVATE
    assert value.public[-1]['role'] == 'assistant'


def test_private_discussion_delivers_into_local_history(adapter):
    value, session, clock = adapter
    value.set_mode('discussion'); value.idle(PRIVATE)
    ready(value, clock)
    history = list(PRIVATE)
    assert value.deliver(lambda text: True, history, lambda: False)
    assert len(history) == 2 and not value.public


def test_mode_switch_during_speech_cannot_copy_private_proposal_to_public(adapter):
    value, session, clock = adapter
    value.set_mode('discussion'); value.idle(PRIVATE)
    ready(value, clock)
    def say(text):
        value.set_mode('animation')
        return True
    history = list(PRIVATE)
    assert not value.deliver(say, history, lambda: False)
    assert not value.public and history == PRIVATE


def test_interruption_discards_unspoken_answer_and_enters_quiet(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([], channels())
    ready(value, clock)
    history = []
    assert not value.deliver(lambda text: False, history, lambda: False)
    assert value.mode == 'quiet' and not history
    clock[0] += 100; value.core.tick()
    assert not value.has_ready()


def test_pending_input_cancels_delivery_without_speaking(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([])
    ready(value, clock)
    say = Mock()
    assert not value.deliver(say, [], lambda: True)
    say.assert_not_called()


def test_mode_change_refreshes_existing_public_snapshot(adapter):
    value, session, clock = adapter
    source = channels()
    value.idle(PRIVATE, source)  # quiet mode can observe public snapshots
    value.set_mode('animation'); value.idle(PRIVATE, source)
    ready(value, clock)
    assert 'validation_public_chess' in repr(session.ask_background.call_args)


def test_rolling_public_snapshot_does_not_repeat_old_turns(adapter):
    value, session, clock = adapter
    first = {'role':'user', 'content':'validation_first'}
    second = {'role':'assistant', 'content':'validation_second'}
    third = {'role':'user', 'content':'validation_third'}
    value.set_mode('animation')
    value.idle([], channels([first, second]))
    ready(value, clock)
    assert value.deliver(lambda text: True, [], lambda: False)
    own = dict(value.public[-1])
    value.idle([], channels([second, third]))
    assert value.public == [second, own, third]
    assert value.core.history == [second, own, third]


def test_expired_public_snapshot_keeps_only_own_delivered_interventions(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([], channels())
    ready(value, clock)
    assert value.deliver(lambda text: True, [], lambda: False)
    own = dict(value.public[-1])
    value.idle([], channels([]))
    assert value.public == [own]
    assert value.core.history == [own]


def test_repeated_mode_does_not_erase_public_context_or_restart_timer(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([], channels())
    due, epoch = value.core.next_attempt, value.core.epoch
    value.set_mode('animation'); value.idle([], channels())
    assert value.public == PUBLIC
    assert value.core.history == PUBLIC
    assert (value.core.next_attempt, value.core.epoch) == (due, epoch)


def test_distinct_equal_public_messages_keep_their_occurrences(adapter):
    value, session, clock = adapter
    repeated = {'role':'user', 'content':'validation_same'}
    later = {'role':'user', 'content':'validation_later'}
    value.set_mode('animation')
    value.idle([], channels([repeated, repeated]))
    value.idle([], channels([repeated, repeated, later]))
    assert value.public == [repeated, repeated, later]
    value.idle([], channels([repeated, later]))
    assert value.public == [repeated, later]


def test_reconnecting_public_context_invalidates_private_proposal(adapter):
    value, session, clock = adapter
    value.set_mode('discussion'); value.idle(PRIVATE, channels())
    value.active(); value.idle(PRIVATE, channels([], enabled=False))
    ready(value, clock)
    proposal = value.core.pop()
    assert proposal is not None
    value.idle(PRIVATE, channels())
    assert not value.core.valid(proposal)
    assert value.core.history == PUBLIC
    assert 'validation_private_secret' not in repr(value.public)


def test_old_snapshot_rows_trimmed_by_own_speech_are_not_replayed(adapter):
    value, session, clock = adapter
    external = [{'role':'user', 'content':'validation_'+str(i)} for i in range(12)]
    value.set_mode('animation'); value.idle([], channels(external))
    ready(value, clock)
    assert value.deliver(lambda text: True, [], lambda: False)
    own = dict(value.public[-1])
    later = {'role':'user', 'content':'validation_new'}
    value.idle([], channels(external[1:]+[later]))
    assert value.public == external[2:]+[own, later]


def test_expiration_after_proposal_ready_prevents_stale_delivery(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([], channels())
    ready(value, clock)
    assert value.refresh_public(channels([]))
    assert not value.has_ready() and value.core.history == []
    say = Mock()
    assert not value.deliver(say, [], lambda: False)
    say.assert_not_called()


def test_public_refresh_does_not_rearm_pending_user_turn(adapter):
    value, session, clock = adapter
    value.set_mode('animation'); value.idle([], channels())
    value.active()
    assert value.refresh_public(channels([]))
    assert value.core.busy
    clock[0] += 100; value.core.tick()
    session.ask_background.assert_not_called()
    value.idle([], channels([]))
    assert not value.core.busy and value.core.history == []


def test_public_snapshot_refresh_leaves_private_discussion_untouched(adapter):
    value, session, clock = adapter
    value.set_mode('discussion'); value.idle(PRIVATE)
    ready(value, clock)
    epoch, history = value.core.epoch, list(value.core.history)
    assert value.refresh_public(channels())
    assert value.has_ready() and value.core.epoch == epoch
    assert value.core.history == history == PRIVATE


def test_public_refresh_in_quiet_mode_does_not_arm_any_speech(adapter):
    value, session, clock = adapter
    assert value.refresh_public(channels())
    assert value.core.busy and value.core.mode == 'quiet'
    clock[0] += 100; value.core.tick()
    session.ask_background.assert_not_called()


@pytest.mark.parametrize('text,mode', [
    ('Je reviens, occupe le stream.', 'animation'),
    ('Alice reste silencieuse !', 'quiet'),
    ('/initiative discussion', 'discussion'),
    ('Un viewer dit: alice occupe le stream', None),
    ('Je parle de rester silencieuse.', None),
])
def test_mode_commands_are_explicit_local_phrases(text, mode):
    assert mode_command(text) == mode
