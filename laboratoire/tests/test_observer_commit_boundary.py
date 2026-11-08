"""Real pending capabilities at a mocked adapter's final dispatch boundary."""
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_checked_actions import CheckedActions
from observer_note_pending import PendingNoteReview
from observer_value_contract import ValueContract


TARGET = {'title': 'Titre', 'body': '<b>Valeur  exacte</b>'}
SAVE = {'op': 'click', 'target': 'save'}


def setup(now=None):
    pending = PendingNoteReview(clock=(lambda: now[0]) if now else lambda: 10)
    pending.propose(TARGET, 'voice')
    auth = pending.confirm(pending.review()['ticket'], 'oui')
    backend = Mock()
    backend._read.return_value = {'elements': [{'id': key, 'value': value} for key, value in TARGET.items()]}
    backend.act.return_value = {'ok': True, 'verified': True, 'reason': 'verified'}
    claim = Mock(side_effect=lambda: pending.claim(auth))
    checked = CheckedActions(backend, ValueContract.from_user_values(TARGET), before_commit=claim)
    return pending, auth, backend, claim, checked


@pytest.mark.parametrize('invalidate', ['cancel', 'correct', 'propose'])
def test_invalidated_authorization_never_reaches_backend(invalidate):
    pending, auth, backend, claim, checked = setup()
    if invalidate == 'cancel':
        pending.cancel()
    elif invalidate == 'correct':
        pending.correct({'title': 'Autre', 'body': 'Nouveau contenu'})
    else:
        pending.propose(TARGET, 'local_text')
    result = checked.act(SAVE, {'issued': True})
    assert not result['ok'] and not result['dispatched']
    assert result['reason'] in ('no_pending_note', 'unknown_or_stale_authorization')
    backend.act.assert_not_called()


def test_mismatched_live_value_does_not_consume_authorization():
    pending, auth, backend, claim, checked = setup()
    backend._read.return_value['elements'][1]['value'] = 'Changed externally'
    result = checked.act(SAVE, {'issued': True})
    assert result['reason'] == 'precommit_values_mismatch'
    assert not result['dispatched']
    claim.assert_not_called()
    backend.act.assert_not_called()
    assert pending.claim(auth) == TARGET


def test_successful_commit_claims_once_and_forwards_original_snapshot():
    pending, auth, backend, claim, checked = setup()
    snapshot = {'issued': 'same-object'}
    result = checked.act(SAVE, snapshot)
    assert result['ok'] and result['dispatched']
    claim.assert_called_once_with()
    assert backend.act.call_args.args == (SAVE, snapshot)
    assert backend.act.call_args.args[1] is snapshot
    backend.observe.assert_not_called()
    with pytest.raises(ValueError):
        pending.claim(auth)
    backend.act.reset_mock()
    result = checked.act(SAVE, snapshot)
    assert not result['ok'] and not result['dispatched']
    backend.act.assert_not_called()


def test_field_edits_and_cancellation_do_not_claim_save_authorization():
    pending, auth, backend, claim, checked = setup()
    checked.act({'op': 'fill', 'target': 'body', 'value_ref': 'user:body'}, {})
    checked.act({'op': 'click', 'target': 'cancel'}, {})
    claim.assert_not_called()
    assert pending.claim(auth) == TARGET


def test_guard_is_checked_before_gate_and_claim():
    pending, auth, backend, claim, checked = setup()
    backend.guard.side_effect = RuntimeError('stopped')
    with pytest.raises(RuntimeError, match='stopped'):
        checked.act(SAVE, {})
    claim.assert_not_called()
    backend._read.assert_not_called()
    backend.act.assert_not_called()
    assert pending.claim(auth) == TARGET


def test_expired_review_cannot_be_dispatched():
    now = [10.0]
    pending, auth, backend, claim, checked = setup(now)
    now[0] = 70.0
    result = checked.act(SAVE, {})
    assert not result['dispatched'] and result['reason'] == 'pending_note_expired'
    backend.act.assert_not_called()


def test_adapter_refusal_after_claim_requires_new_review():
    pending, auth, backend, claim, checked = setup()
    backend.act.return_value = {'ok': False, 'verified': False, 'reason': 'observation_changed'}
    result = checked.act(SAVE, {})
    assert not result['ok'] and result['reason'] == 'observation_changed'
    with pytest.raises(ValueError, match='no_pending_note'):
        pending.claim(auth)


def test_runtime_failure_of_callback_propagates_without_dispatch():
    pending, auth, backend, claim, checked = setup()
    claim.side_effect = RuntimeError('review service unavailable')
    with pytest.raises(RuntimeError, match='review service unavailable'):
        checked.act(SAVE, {})
    backend.act.assert_not_called()


def test_cancellation_wins_if_it_precedes_claim_inside_callback():
    pending, auth, backend, claim, checked = setup()
    def cancel_then_claim():
        pending.cancel()
        return pending.claim(auth)
    claim.side_effect = cancel_then_claim
    result = checked.act(SAVE, {})
    assert not result['ok'] and not result['dispatched']
    backend.act.assert_not_called()
