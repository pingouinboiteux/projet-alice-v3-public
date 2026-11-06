import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_note_pending import Authorization, PendingNoteReview


TARGET = {'title': 'Été', 'body': '<b>Garder  deux espaces</b>\n15,60 EUR'}


def prepared(clock=lambda: 10):
    state = PendingNoteReview(clock=clock)
    state.propose(TARGET, 'voice')
    ticket = state.review()
    return state, ticket


def test_review_confirm_and_claim_preserve_exact_values():
    state, review = prepared()
    assert review['source'] == 'voice'
    auth = state.confirm(review['ticket'], 'je confirme')
    with pytest.raises(FrozenInstanceError):
        auth.version = 99
    assert state.claim(auth) == TARGET
    with pytest.raises(ValueError, match='no_pending_note'):
        state.claim(auth)


def test_external_dictionary_mutations_cannot_change_reviewed_note():
    target = dict(TARGET)
    state = PendingNoteReview()
    state.propose(target, 'local_text')
    target['body'] = 'mutated'
    review = state.review()
    review['target']['body'] = 'also mutated'
    auth = state.confirm(review['ticket'], 'oui')
    assert state.claim(auth) == TARGET


def test_correction_invalidates_ticket_and_authorization():
    state, old = prepared()
    auth = state.confirm(old['ticket'], 'oui')
    new_version = state.correct({'title': 'Nouveau', 'body': 'Valeur corrigée'})
    assert new_version > old['version']
    with pytest.raises(ValueError, match='unknown_or_stale_review'):
        state.confirm(old['ticket'], 'oui')
    with pytest.raises(ValueError, match='unknown_or_stale_authorization'):
        state.claim(auth)
    new = state.review()
    assert state.claim(state.confirm(new['ticket'], 'oui'))['body'] == 'Valeur corrigée'


def test_cancel_invalidates_pending_capabilities_and_cannot_revive():
    state, ticket = prepared()
    auth = state.confirm(ticket['ticket'], 'oui')
    state.cancel()
    for action in [lambda: state.claim(auth), lambda: state.review(),
                   lambda: state.confirm(ticket['ticket'], 'oui')]:
        with pytest.raises(ValueError, match='no_pending_note'):
            action()


def test_second_review_invalidates_previous_ticket_and_authorization():
    state, first = prepared()
    auth = state.confirm(first['ticket'], 'oui')
    second = state.review()
    assert first['ticket'] != second['ticket']
    with pytest.raises(ValueError):
        state.claim(auth)
    assert state.claim(state.confirm(second['ticket'], 'oui')) == TARGET


def test_confirmation_is_one_use():
    state, ticket = prepared()
    state.confirm(ticket['ticket'], 'oui')
    with pytest.raises(ValueError, match='unknown_or_stale_review'):
        state.confirm(ticket['ticket'], 'oui')


def test_forged_and_copied_authorization_cannot_be_claimed():
    state, ticket = prepared()
    auth = state.confirm(ticket['ticket'], 'oui')
    for forged in [Authorization(auth.version, auth.nonce), copy.copy(auth), None, {'version': auth.version}]:
        with pytest.raises(ValueError, match='unknown_or_stale_authorization'):
            state.claim(forged)
    assert state.claim(auth) == TARGET


@pytest.mark.parametrize('source', ['voice', 'page', 'chat', 'ocr', None])
def test_only_local_text_can_confirm(source):
    state, ticket = prepared()
    with pytest.raises(ValueError, match='explicit_local_text_confirmation_required'):
        state.confirm(ticket['ticket'], 'oui', source)


@pytest.mark.parametrize('response', ['oui mais change le texte', 'non', '', 'Oui', True])
def test_confirmation_is_explicit_exact_not_embedded(response):
    state, ticket = prepared()
    with pytest.raises(ValueError, match='explicit_confirmation_required'):
        state.confirm(ticket['ticket'], response)


def test_expiry_applies_to_authorization_and_review_cannot_extend_it():
    now = [10.0]
    state, first = prepared(lambda: now[0])
    now[0] = 69.0
    review = state.review()
    assert review['expires_at'] == first['expires_at']
    auth = state.confirm(review['ticket'], 'oui')
    now[0] = 70.0
    with pytest.raises(ValueError, match='pending_note_expired'):
        state.claim(auth)


def test_clock_rollback_invalidates_pending_state():
    now = [10.0]
    state, ticket = prepared(lambda: now[0])
    now[0] = 9
    with pytest.raises(ValueError, match='invalid_monotonic_clock'):
        state.confirm(ticket['ticket'], 'oui')
    now[0] = 11
    with pytest.raises(ValueError, match='no_pending_note'):
        state.review()


@pytest.mark.parametrize('ttl', [0, -1, 61, True, float('inf'), float('nan')])
def test_ttl_bounds(ttl):
    with pytest.raises(ValueError):
        PendingNoteReview(ttl_seconds=ttl)


@pytest.mark.parametrize('source', ['page', 'ocr', 'confirmed_voice', None])
def test_untrusted_proposal_source_refused(source):
    with pytest.raises(ValueError, match='untrusted_input_source'):
        PendingNoteReview().propose(TARGET, source)


def test_new_proposal_invalidates_old_authorization():
    state, ticket = prepared()
    auth = state.confirm(ticket['ticket'], 'oui')
    state.propose({'title': 'Autre', 'body': 'Autre texte'}, 'voice')
    with pytest.raises(ValueError, match='unknown_or_stale_authorization'):
        state.claim(auth)


def test_non_ascii_ticket_refuses_cleanly():
    state, _ = prepared()
    with pytest.raises(ValueError, match='unknown_or_stale_review'):
        state.confirm('échec', 'oui')


@pytest.mark.parametrize('target', [
    {'title': 'x', 'body': 'y', 'extra': 'z'}, {'title': 'x', 'body': True},
    {'title': '$:/config', 'body': 'y'}, {'title': 'x\ny', 'body': 'z'},
    {'title': 'x', 'body': '   '},
])
def test_note_schema_and_bounds(target):
    with pytest.raises(ValueError):
        PendingNoteReview().propose(target, 'local_text')


def test_cancel_racing_claim_has_only_one_commit_boundary():
    for _ in range(20):
        state, ticket = prepared()
        auth = state.confirm(ticket['ticket'], 'oui')
        start = threading.Barrier(2)
        def claim():
            start.wait()
            try:
                return state.claim(auth)
            except ValueError:
                return None
        def cancel():
            start.wait()
            return state.cancel()
        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed, cancelled = pool.submit(claim), pool.submit(cancel)
            result = claimed.result()
            cancelled.result()
        assert result is None or result == TARGET
        with pytest.raises(ValueError):
            state.claim(auth)
