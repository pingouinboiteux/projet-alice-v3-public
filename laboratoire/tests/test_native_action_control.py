"""Contract tests only: no Windows input, personal window or model."""
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_action_control import NativeActionControl


def setup():
    state = {'window': {'hwnd': 12, 'pid': 34, 'created': 56},
             'foreground': True, 'available': True, 'geometry': [0, 0, 300, 200],
             'elements': [{'id': 'edit', 'enabled': True, 'visible': True,
                           'focused': True, 'actions': ['type', 'key', 'click'],
                           'allowed_keys': ['Tab'], 'value': ''}]}
    now = [10.0]
    adapter = Mock()
    adapter.read.side_effect = lambda: deepcopy(state)
    adapter.dispatch.side_effect = lambda action, **kw: state['elements'][0].update(value=action.get('text', ''))
    control = NativeActionControl(adapter, state['window'], lambda: None, clock=lambda: now[0])
    return control, adapter, state, now


ACTION = {'op': 'type', 'target': 'edit', 'text': 'validation_texte'}


def verified(action, before, after):
    return after['elements'][0]['value'] == action['text']


def test_success_requires_independent_read_and_single_use():
    c, a, s, _ = setup(); snap = c.observe()
    assert c.act(ACTION, snap, verified)['status'] == 'verified'
    assert a.read.call_count == 3
    assert c.act(ACTION, snap, verified)['status'] == 'refused'
    assert a.dispatch.call_count == 1


@pytest.mark.parametrize('change', ['focus', 'window', 'geometry', 'closed', 'element', 'modified', 'expired', 'clock_back', 'stop'])
def test_changed_context_never_dispatches(change):
    c, a, s, now = setup(); snap = c.observe()
    if change == 'focus': s['foreground'] = False
    if change == 'window': s['window']['created'] += 1
    if change == 'geometry': s['geometry'][0] += 1
    if change == 'closed': s['available'] = False
    if change == 'element': s['elements'][0]['value'] = 'user typing'
    if change == 'modified': snap['state']['elements'][0]['value'] = 'forged'
    if change == 'expired': now[0] += 4
    if change == 'clock_back': now[0] -= 1
    if change == 'stop': c.stop()
    assert c.act(ACTION, snap, verified)['status'] == 'refused'
    a.dispatch.assert_not_called()


def test_expiry_during_read_is_rejected():
    c, a, s, now = setup(); snap = c.observe()
    def slow_read():
        now[0] += 4
        return deepcopy(s)
    a.read.side_effect = slow_read
    assert c.act(ACTION, snap, verified)['reason'] == 'native_observation_expired'
    a.dispatch.assert_not_called()


@pytest.mark.parametrize('fault', ['disabled', 'hidden', 'unfocused', 'duplicate', 'missing'])
def test_invalid_target_before_observation(fault):
    c, a, s, _ = setup()
    if fault == 'disabled': s['elements'][0]['enabled'] = False
    if fault == 'hidden': s['elements'][0]['visible'] = False
    if fault == 'unfocused': s['elements'][0]['focused'] = False
    if fault == 'duplicate': s['elements'] *= 2
    if fault == 'missing': s['elements'] = []
    assert c.act(ACTION, c.observe(), verified)['status'] == 'refused'
    a.dispatch.assert_not_called()


def test_exception_after_input_is_uncertain_and_not_retried():
    c, a, s, _ = setup(); snap = c.observe()
    def partial(*args, **kwargs):
        s['elements'][0]['value'] = 'validation_'
        raise TimeoutError()
    a.dispatch.side_effect = partial
    assert c.act(ACTION, snap, verified)['status'] == 'uncertain'
    assert c.act(ACTION, snap, verified)['status'] == 'refused'
    assert a.dispatch.call_count == 1


def test_sent_is_not_success():
    c, a, s, _ = setup(); a.dispatch.side_effect = None
    assert c.act(ACTION, c.observe(), verified)['status'] == 'unverified'


def test_shortcuts_are_bound_to_observed_control():
    c, a, s, _ = setup()
    assert c.act({'op': 'key', 'target': 'edit', 'key': 'Alt+F4'}, c.observe(), lambda *a: True)['status'] == 'refused'
    a.dispatch.assert_not_called()


def test_stop_during_dispatch_prevents_success():
    c, a, s, _ = setup(); a.dispatch.side_effect = lambda *a, **k: c.stop()
    assert c.act(ACTION, c.observe(), verified)['status'] == 'uncertain'
    a.cancel.assert_called_once()


def test_last_guard_cannot_extend_observation_lifetime():
    c, a, s, now = setup(); snap = c.observe()
    calls = [0]
    def slow_last_guard():
        calls[0] += 1
        if calls[0] == 4:
            now[0] += 4
    c.guard = slow_last_guard
    assert c.act(ACTION, snap, verified)['status'] == 'refused'
    a.dispatch.assert_not_called()


def test_dispatch_cannot_change_expected_text():
    c, a, s, _ = setup()
    def mutate(action, **kwargs):
        action['text'] = 'wrong'
        s['elements'][0]['value'] = 'wrong'
    a.dispatch.side_effect = mutate
    assert c.act(ACTION, c.observe(), verified)['status'] == 'unverified'


def test_stop_during_verification_is_not_success():
    c, a, s, _ = setup()
    def stopping_verifier(*args):
        c.stop()
        return True
    assert c.act(ACTION, c.observe(), stopping_verifier)['status'] == 'uncertain'


def test_adapter_cancellation_includes_expiry():
    c, a, s, now = setup()
    def waiting_adapter(action, *, expected, cancelled):
        assert not cancelled()
        now[0] += 4
        assert cancelled()
        raise TimeoutError()
    a.dispatch.side_effect = waiting_adapter
    assert c.act(ACTION, c.observe(), verified)['status'] == 'uncertain'
