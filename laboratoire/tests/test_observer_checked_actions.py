"""Independent precommit boundary checks; no browser, model or network."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_checked_actions import CheckedActions
from observer_value_contract import ValueContract


def build(values=None):
    values = values or {'title': '<b>exact</b>', 'reminder': False}
    backend = Mock()
    backend._read.return_value = {'elements': [{'id': field, 'value': value} for field, value in values.items()]}
    backend.act.return_value = {'ok': True, 'verified': True, 'reason': 'verified'}
    return backend, CheckedActions(backend, ValueContract.from_user_values(values))


def test_wrong_live_value_prevents_commit_even_if_snapshot_claims_correct():
    backend, checked = build()
    snapshot = backend._read.return_value
    backend._read.return_value = {'elements': [{'id': 'title', 'value': 'exact'}, {'id': 'reminder', 'value': False}]}
    result = checked.act({'op': 'click', 'target': 'save'}, snapshot)
    assert result['reason'] == 'precommit_values_mismatch'
    assert not result['dispatched'] and not result['ok']
    backend.act.assert_not_called()


@pytest.mark.parametrize('elements', [
    [{'id': 'title', 'value': '<b>exact</b>'}],
    [{'id': 'title', 'value': '<b>exact</b>'}, {'id': 'reminder', 'value': 0}],
    [{'id': 'title', 'value': '<b>exact</b>'}, {'id': 'title', 'value': '<b>exact</b>'}, {'id': 'reminder', 'value': False}],
])
def test_missing_type_changed_or_duplicate_fields_block_commit(elements):
    backend, checked = build()
    backend._read.return_value = {'elements': elements}
    result = checked.act({'op': 'click', 'target': 'save'}, {'issued': True})
    assert not result['ok'] and not result['dispatched']
    backend.act.assert_not_called()


def test_correct_values_do_not_replace_stale_snapshot_with_new_capability():
    backend, checked = build()
    snapshot = {'issued': 'old'}
    backend.act.return_value = {'ok': False, 'verified': False, 'reason': 'observation_changed'}
    result = checked.act({'op': 'click', 'target': 'save'}, snapshot)
    assert not result['ok'] and result['reason'] == 'observation_changed'
    assert backend.act.call_args.args[1] is snapshot
    backend.observe.assert_not_called()


def test_reference_inserts_exact_text_but_keeps_original_snapshot():
    backend, checked = build({'body': '  <b>e\u0301</b>\nline 2 '})
    snapshot = {'issued': 'same'}
    result = checked.act({'op': 'fill', 'target': 'body', 'value_ref': 'user:body'}, snapshot)
    assert result['ok']
    assert backend.act.call_args.args == ({'op': 'fill', 'target': 'body', 'value': '  <b>e\u0301</b>\nline 2 '}, snapshot)
    backend._read.assert_not_called()


@pytest.mark.parametrize('action', [
    {'op': 'fill', 'target': 'title', 'value': 'exact'},
    {'op': 'fill', 'target': 'title', 'value_ref': 'user:reminder'},
    {'op': 'fill', 'target': 'external', 'value': 'unapproved'},
    {'op': 'fill', 'target': 'title', 'value': '<b>exact</b>', 'shell': 'x'},
    {'op': 'click', 'target': 'save', 'value': 'bypass'},
    {'op': 'execute', 'target': 'save'},
    ['click', 'save'],
])
def test_unapproved_or_invalid_changes_never_reach_backend(action):
    backend, checked = build()
    result = checked.act(action, {'issued': True})
    assert not result['ok'] and not result['dispatched']
    backend.act.assert_not_called()


def test_guard_failure_prevents_live_read_and_dispatch():
    backend, checked = build()
    backend.guard.side_effect = RuntimeError('fps_guard_stopped')
    with pytest.raises(RuntimeError, match='fps_guard_stopped'):
        checked.act({'op': 'click', 'target': 'save'}, {})
    backend._read.assert_not_called()
    backend.act.assert_not_called()


def test_backend_runtime_failure_is_not_reported_as_clean_refusal():
    backend, checked = build()
    backend.act.side_effect = RuntimeError('interrupted_after_dispatch')
    with pytest.raises(RuntimeError, match='interrupted_after_dispatch'):
        checked.act({'op': 'click', 'target': 'save'}, {})


def test_backend_value_error_after_dispatch_is_not_a_clean_refusal():
    backend, checked = build()
    backend.act.side_effect = ValueError('invalid_postcondition_after_dispatch')
    with pytest.raises(ValueError, match='invalid_postcondition_after_dispatch'):
        checked.act({'op': 'click', 'target': 'save'}, {})


def test_saved_success_uses_strict_types_and_exact_fields():
    from observer_value_bench import saved_exact
    target = {'reminder': False, 'title': '<b>x</b>'}
    contract = ValueContract.from_user_values(target)
    assert saved_exact({'saved': target.copy()}, target, contract)
    assert not saved_exact({'saved': {'reminder': 0, 'title': '<b>x</b>'}}, target, contract)
    assert not saved_exact({'saved': {'reminder': False, 'title': 'x'}}, target, contract)
    assert not saved_exact({'saved': dict(target, extra='unexpected')}, target, contract)
    assert not saved_exact({'saved': None}, target, contract)


def test_valid_save_requires_live_read_before_dispatch():
    backend, checked = build()
    events = []
    backend.guard.side_effect = lambda: events.append('guard')
    current = backend._read.return_value
    backend._read.side_effect = lambda: events.append('read') or current
    backend.act.side_effect = lambda *args: events.append('dispatch') or {'ok': True, 'verified': True}
    result = checked.act({'op': 'click', 'target': 'save'}, {})
    assert result['ok'] and result['precommit']['ok']
    assert events == ['guard', 'read', 'dispatch']
