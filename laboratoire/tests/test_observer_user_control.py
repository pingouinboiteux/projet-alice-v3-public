import re
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_user_control import ControlPattern, control_text
from observer_note_intent import validate_intent
from observer_note_revision import revision_state, payload_for_revision


def plan(title, body, title_turn=0, body_turn=0):
    return {'intent': 'create_note', 'title': {'turn': title_turn, 'quote': title},
            'body': {'turn': body_turn, 'quote': body}}


@pytest.mark.parametrize('opening,closing', [('"','"'), ('«','»'), ('“','”')])
def test_quoted_controls_are_masked_and_offsets_preserved(opening, closing):
    text = f'Avant {opening}stop et titre{closing} puis annule'
    masked = control_text(text)
    assert len(masked) == len(text)
    assert 'stop' not in masked and 'titre' not in masked
    assert masked.index('annule') == text.index('annule')


def test_apostrophes_are_not_data_delimiters():
    text = "N'enregistre pas l’été et ne sauvegarde pas l'autre note"
    assert control_text(text) == text


def test_nested_quote_pairs_and_escaped_double_quotes():
    text = 'Crée une note «un "titre" et “stop”» puis annule'
    masked = control_text(text)
    assert 'titre' not in masked and 'stop' not in masked and 'annule' in masked
    escaped = r'Crée une note texte "Dire \"stop\" ici" puis annule'
    assert 'stop' not in control_text(escaped)
    assert 'annule' in control_text(escaped)


def test_newlines_in_quotes_keep_positions_without_exposing_data():
    text = 'texte "première\nstop" puis annule'
    masked = control_text(text)
    assert len(masked) == len(text) and masked.count('\n') == 1
    assert 'stop' not in masked


@pytest.mark.parametrize('text', ['texte "stop', 'texte «stop', 'texte “stop',
                                 'texte stop»', 'texte «stop”'])
def test_unbalanced_quotes_fail_closed(text):
    with pytest.raises(ValueError, match='unbalanced_user_quotes'):
        control_text(text)
    assert ControlPattern(re.compile('stop')).search(text) is None


def test_wrapper_reports_original_control_match_position():
    text = '"stop" puis stop'
    match = ControlPattern(re.compile('stop')).search(text)
    assert match.start() == text.rindex('stop')


@pytest.mark.parametrize('opening,closing', [('"','"'), ('«','»'), ('“','”')])
def test_note_with_literal_stop_is_not_cancelled(opening, closing):
    text = f'Crée une note titre {opening}Stop{closing} et texte {opening}Annule la dernière ligne{closing}.'
    result = validate_intent(plan('Stop', 'Annule la dernière ligne'), [text])
    assert result['status'] == 'ready'
    assert result['target'] == {'title':'Stop', 'body':'Annule la dernière ligne'}


def test_cancellation_outside_quotes_still_wins():
    turns = ['Crée une note titre "Signal" et texte "Dire stop".',
             'Garde le mot "stop", mais annule cette demande.']
    result = validate_intent(plan('Signal', 'Dire stop'), turns)
    assert result['status'] == 'cancel'


def test_quoted_field_label_does_not_invalidate_another_field():
    turns = ['Crée une note titre "Titre initial" et texte "Ancienne valeur".',
             'Remplace le texte par "Le titre reste identique".']
    result = validate_intent(plan('Titre initial', 'Le titre reste identique', body_turn=1), turns)
    assert result['status'] == 'ready'
    state = revision_state(turns)
    assert state['fields']['title']['eligible_source_turns'] == [0,1]
    assert state['fields']['body']['eligible_source_turns'] == [1]


def test_quoted_correction_does_not_supersede_values():
    turns = ['Crée une note titre "Projet" et texte "Valeur finale".',
             'Je cite seulement "remplace le titre".']
    result = validate_intent(plan('Projet', 'Valeur finale'), turns)
    assert result['status'] == 'ready'


def test_quote_cannot_supply_a_creation_command():
    turns = ['"Crée une note" titre "Projet" et texte "Valeur".']
    result = validate_intent(plan('Projet', 'Valeur'), turns)
    assert result['status'] == 'clarify'
    assert result['reason'] == 'explicit_creation_request_required'


def test_unclosed_quote_returns_clarification_even_with_model_ready():
    turns = ['Crée une note titre "Projet" et texte "Valeur']
    result = validate_intent(plan('Projet', 'Valeur'), turns)
    assert result['status'] == 'clarify' and result['reason'] == 'unbalanced_user_quotes'
    assert 'target' not in result


def test_unclosed_quotes_do_not_crash_candidate_prompt_preparation():
    turns = ['Crée une note titre "Projet" et texte "Valeur']
    payload = payload_for_revision(turns)
    assert len(payload['messages']) == 2
    assert 'Valeur' in payload['messages'][1]['content']
    assert validate_intent(plan('Projet', 'Valeur'), turns)['status'] == 'clarify'


def test_literal_values_and_citation_offsets_are_untouched():
    turns = ['Crée une note titre "Étude" et texte «<b>stop</b>  l’été».']
    result = validate_intent(plan('Étude', '<b>stop</b>  l’été'), turns)
    assert result['status'] == 'ready'
    ref = result['sources']['body']
    assert turns[0][ref['start']:ref['end']] == '<b>stop</b>  l’été'
