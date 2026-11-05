"""Synthetic scheduler tests; no model, microphone, memory or network."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from conversation_initiative import Initiative


HISTORY = [{'role': 'user', 'content': 'Les jeux de strategie me plaisent.'},
           {'role': 'assistant', 'content': 'Choisir sous incertitude les rend interessants.'}]


def fixture(choice='continue', reply='On peut aussi gagner en laissant croire que notre plan est ailleurs.'):
    now = [0.]
    session = SimpleNamespace(ask_background=Mock(return_value=(json.dumps({'choice': choice, 'reply': reply}), 0, {})))
    engine = Initiative(session, clock=lambda: now[0], discussion_delay=10, animation_delay=3, retry_delay=20)
    return engine, session, now


def enable(engine, mode='discussion', history=None):
    engine.set_mode(mode)
    engine.idle(HISTORY if history is None else history, public=mode == 'animation')


def test_initial_quiet_and_empty_discussion_do_not_invoke_model():
    engine, session, now = fixture()
    engine.idle(HISTORY); now[0] = 100; engine.tick()
    enable(engine, history=[]); now[0] = 200; engine.tick()
    session.ask_background.assert_not_called()


def test_repeated_idle_does_not_postpone_deadline():
    engine, session, now = fixture(); enable(engine)
    for second in range(1, 11):
        now[0] = second; engine.idle(list(HISTORY)); engine.tick()
    assert engine.has_ready()
    assert session.ask_background.call_count == 1


def test_generation_and_pop_do_not_schedule_next_speech_before_delivery():
    engine, session, now = fixture(); enable(engine)
    now[0] = 10; engine.tick(); now[0] = 100; engine.tick()
    proposal = engine.pop(); assert engine.valid(proposal)
    engine.tick(); assert session.ask_background.call_count == 1
    engine.delivered(proposal)
    now[0] = 109; engine.tick(); assert session.ask_background.call_count == 1
    now[0] = 110; engine.tick(); assert session.ask_background.call_count == 2
    assert not engine.has_ready()  # The exact same speech is not repeated.


def test_delivered_context_contains_only_spoken_prefix():
    engine, session, now = fixture(); enable(engine)
    now[0] = 10; engine.tick(); proposal = engine.pop()
    assert engine.delivered(proposal, 'On peut aussi')
    assert engine.history[-1]['content'] == 'On peut aussi'
    assert not engine.delivered(proposal)
    engine.idle(HISTORY)  # A repeated owner snapshot must not erase delivered text.
    assert engine.history[-1]['content'] == 'On peut aussi'


def test_new_user_turn_invalidates_ready_and_popped_reply():
    engine, session, now = fixture(); enable(engine)
    now[0] = 10; engine.tick(); proposal = engine.pop()
    engine.active()
    assert not engine.valid(proposal) and not engine.delivered(proposal)
    assert not engine.has_ready()


@pytest.mark.parametrize('invalidate', ['active', 'quiet', 'history', 'close'])
def test_late_completion_discarded(invalidate):
    engine, session, now = fixture(); enable(engine)
    result = session.ask_background.return_value
    def complete(*args):
        if invalidate == 'active': engine.active()
        elif invalidate == 'quiet': engine.set_mode('quiet')
        elif invalidate == 'history': engine.idle([{'role': 'user', 'content': 'Autre sujet.'}])
        else: engine.close()
        return result
    session.ask_background.side_effect = complete
    now[0] = 10; engine.tick()
    assert not engine.has_ready()


def test_animation_accepts_empty_public_context_but_never_private_context():
    engine, session, now = fixture(); enable(engine)
    engine.set_mode('animation')
    assert not engine.history
    with pytest.raises(ValueError): engine.idle(HISTORY)
    now[0] = 100; engine.tick(); session.ask_background.assert_not_called()
    engine.idle([], public=True); now[0] = 103; engine.tick()
    assert engine.has_ready()
    payload = json.loads(session.ask_background.call_args.args[0][1]['content'])
    assert payload == {'mode': 'animation', 'historique': [], 'contexte_actualise':False}


@pytest.mark.parametrize('raw', [None, 'broken', '{}', '{"choice":"wait","reply":"Non vide"}',
    '{"choice":"continue","reply":""}', '{"choice":"tool","reply":"execute"}',
    json.dumps({'choice': 'continue', 'reply': 'a' * 601}),
    json.dumps({'choice': 'continue', 'reply': 'a ' * 101})])
def test_busy_model_and_invalid_output_back_off_without_speech(raw):
    engine, session, now = fixture(); enable(engine)
    session.ask_background.return_value = None if raw is None else (raw, 0, {})
    now[0] = 10; engine.tick(); assert not engine.has_ready()
    now[0] = 29; engine.tick(); assert session.ask_background.call_count == 1
    now[0] = 30; engine.tick(); assert session.ask_background.call_count == 2


def test_wait_choice_uses_retry_delay_and_does_not_repeat_every_tick():
    engine, session, now = fixture('wait', ''); enable(engine)
    now[0] = 10; engine.tick()
    for second in range(11, 30): now[0] = second; engine.tick()
    assert session.ask_background.call_count == 1 and not engine.has_ready()


def test_wait_acknowledgement_is_never_spoken_and_is_a_valid_decision():
    engine, session, now = fixture('wait', 'Je te laisse reflechir.'); enable(engine)
    now[0] = 10; engine.tick()
    assert engine.last_outcome == 'wait'
    assert engine.last_error is None
    assert not engine.has_ready()


def test_slow_wait_backoff_starts_after_inference():
    engine, session, now = fixture('wait', ''); enable(engine)
    result = session.ask_background.return_value
    def complete(*args): now[0] += 100; return result
    session.ask_background.side_effect = complete
    now[0] = 10; engine.tick(); engine.tick()
    assert session.ask_background.call_count == 1


def test_context_is_bounded_with_whole_messages():
    engine, session, now = fixture()
    history = [{'role': 'user', 'content': str(index) * 2000} for index in range(9)]
    enable(engine, history=history)
    assert len(engine.history) == 3
    assert sum(len(m['content']) for m in engine.history) == 6000


def test_model_exception_backoff_and_close_prevents_restart():
    engine, session, now = fixture(); enable(engine)
    session.ask_background.side_effect = RuntimeError('synthetic failure')
    now[0] = 10; engine.tick(); assert not engine.has_ready()
    engine.close(); engine.start(); assert engine.thread is None
    now[0] = 100; engine.tick(); assert session.ask_background.call_count == 1


@pytest.mark.parametrize('delay', [0, -1, float('nan'), float('inf')])
def test_invalid_delays_rejected(delay):
    with pytest.raises(ValueError): Initiative(None, retry_delay=delay)


def test_single_inflight_call_even_if_tick_reentered():
    engine, session, now = fixture(); enable(engine)
    result = session.ask_background.return_value
    def complete(*args): now[0] += 100; engine.tick(); return result
    session.ask_background.side_effect = complete
    now[0] = 10; engine.tick()
    assert session.ask_background.call_count == 1
