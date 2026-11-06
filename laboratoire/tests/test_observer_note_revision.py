import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_note_revision import payload_for_revision, revision_state, SCHEMA
from observer_note_intent import validate_intent, SCHEMA as ORIGINAL_SCHEMA


def test_body_correction_keeps_title_sources_but_invalidates_old_body():
    turns = ['Cree une note titre "Rdv" et texte "Mardi".',
             'Finalement, remplace le texte par "Jeudi".']
    state = revision_state(turns)
    assert state['fields']['title']['eligible_source_turns'] == [0, 1]
    assert state['fields']['body']['eligible_source_turns'] == [1]
    assert state['fields']['body']['must_reextract_after_correction']
    old = {'intent': 'create_note', 'title': {'turn': 0, 'quote': 'Rdv'},
           'body': {'turn': 0, 'quote': 'Mardi'}}
    assert validate_intent(old, turns)['reason'] == 'citation_superseded_by_correction'


def test_separate_revisions_apply_to_their_fields_only():
    state = revision_state(['Cree une note titre A texte B.',
                            'Change le titre en C.', 'Remplace le contenu par D.'])
    assert state['fields']['title']['eligible_source_turns'] == [1, 2]
    assert state['fields']['body']['eligible_source_turns'] == [2]


def test_unnamed_correction_is_conservative_for_both_fields():
    state = revision_state(['Cree une note titre A texte B.', 'Non, plutot autre chose.'])
    assert all(value['eligible_source_turns'] == [1] for value in state['fields'].values())


def test_clarification_answer_does_not_drop_original_request():
    state = revision_state(['Cree une note pour demain.', 'Titre Jardin, texte Eau.'])
    assert state['active_creation_turn'] == 0
    assert all(value['eligible_source_turns'] == [0, 1] for value in state['fields'].values())


@pytest.mark.parametrize('turns', [
    ['Explique comment creer une note.'],
    ['Cree une note titre A texte B.', 'Annule.', 'Oui'],
])
def test_no_active_request_has_no_eligible_sources(turns):
    state = revision_state(turns)
    assert state['active_creation_turn'] is None
    assert all(value['eligible_source_turns'] == [] for value in state['fields'].values())


def test_new_request_resets_source_minimum():
    state = revision_state(['Cree une note titre A texte B.', 'Annule.',
                            'Cree une note titre C texte D.'])
    assert state['active_creation_turn'] == 2
    assert all(value['eligible_source_turns'] == [2] for value in state['fields'].values())


def test_all_original_texts_preserved_and_no_target_injected():
    turns = ['Cree une note titre "<b>" texte "  deux espaces".',
             'Corrige le texte par "e\u0301".']
    before = list(turns)
    payload = payload_for_revision(turns)
    user = json.loads(payload['messages'][1]['content'])
    assert user['trusted_user_turns'] == [{'turn': i, 'text': t} for i, t in enumerate(turns)]
    assert 'target' not in user and 'expected' not in user
    assert turns == before
    assert SCHEMA is ORIGINAL_SCHEMA


def test_budget_and_type_checks_are_shared():
    with pytest.raises(ValueError):
        payload_for_revision(['x'] * 9)
    with pytest.raises(ValueError):
        revision_state('not a list')
