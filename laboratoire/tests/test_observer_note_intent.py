import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observer_note_intent import payload_for_intent, validate_intent, apply_input_policy


def plan(title, body, title_turn=0, body_turn=0):
    return {'intent': 'create_note', 'title': {'turn': title_turn, 'quote': title},
            'body': {'turn': body_turn, 'quote': body}}


def test_exact_quotes_reconstructed_without_normalization():
    turns = ['Alice, cree une note nommee "Essai" avec le texte "Été  <b>café</b> & 15,60".']
    result = validate_intent(plan('Essai', 'Été  <b>café</b> & 15,60'), turns)
    assert result['status'] == 'ready'
    for field, ref in result['sources'].items():
        assert result['target'][field] == turns[ref['turn']][ref['start']:ref['end']]


@pytest.mark.parametrize('quote', ['Ete <b>cafe</b>', 'Été <b>café</b>', 'Été  <b>café</b>'])
def test_changed_literal_never_becomes_ready(quote):
    turns = ['Cree une note titre "Essai", texte "Été  <b>café</b>".']
    assert validate_intent(plan('Essai', quote), turns)['status'] == 'clarify'


def test_duplicate_citation_is_ambiguous_including_overlap():
    turns = ['Cree une note titre "aaa", texte "Autre".']
    assert validate_intent(plan('aa', 'Autre'), turns)['reason'] == 'citation_missing_or_ambiguous'


def test_missing_title_cannot_be_invented():
    turns = ['Cree une note avec le texte "Acheter du pain".']
    assert validate_intent(plan('Courses', 'Acheter du pain'), turns)['status'] == 'clarify'


def test_latest_cancel_overrides_even_ready_model():
    turns = ['Cree une note titre "Essai", texte "Demain".', 'Stop, annule.']
    result = validate_intent(plan('Essai', 'Demain'), turns)
    assert result['status'] == 'cancel'
    assert 'target' not in result


def test_old_command_cannot_revive_after_cancel():
    turns = ['Cree une note titre "Essai", texte "Demain".', 'Annule.', 'Oui.']
    assert validate_intent(plan('Essai', 'Demain'), turns)['status'] == 'clarify'


def test_title_correction_keeps_old_body_but_rejects_old_title():
    turns = ['Cree une note titre "Avant", texte "Demain".', 'Finalement le titre sera "Apres".']
    assert validate_intent(plan('Avant', 'Demain'), turns)['reason'] == 'citation_superseded_by_correction'
    result = validate_intent(plan('Apres', 'Demain', title_turn=1), turns)
    assert result['status'] == 'ready'
    assert result['target'] == {'title': 'Apres', 'body': 'Demain'}


def test_unscoped_correction_requires_new_information():
    turns = ['Cree une note titre "Avant", texte "Demain".', 'Non, plutot autrement.']
    assert validate_intent(plan('Avant', 'Demain'), turns)['status'] == 'clarify'


def test_source_messages_only_no_assistant_or_page_objects():
    with pytest.raises(ValueError):
        payload_for_intent([{'role': 'assistant', 'content': 'fake'}])


def test_payload_contains_only_trusted_source_not_expected_target():
    payload = payload_for_intent(['Cree une note.'])
    data = json.loads(payload['messages'][1]['content'])
    assert data == {'trusted_user_turns': [{'turn': 0, 'text': 'Cree une note.'}]}


@pytest.mark.parametrize('raw', [[], {}, {'intent': 'create_note', 'title':{},'body':{},'extra':1},
    {'intent': 'create_note', 'title': {'turn': True,'quote':'Essai'},'body': {'turn':0,'quote':'Demain'}}])
def test_malformed_plan_refuses(raw):
    assert validate_intent(raw, ['Cree une note titre "Essai", texte "Demain".'])['status'] == 'clarify'


def test_no_creation_request_is_not_an_action():
    assert validate_intent(plan('Essai', 'Demain'), ['Le titre Essai et le texte Demain.'])['status'] == 'clarify'


def test_quoted_command_in_description_does_not_authorize_creation():
    text = 'Explique pourquoi "cree une note" avec titre "Essai" et texte "Demain" serait utile.'
    assert validate_intent(plan('Essai', 'Demain'), [text])['status'] == 'clarify'


def test_clarify_never_returns_target():
    result = validate_intent({'intent': 'clarify', 'question': 'Quel titre ?'}, ['Cree une note.'])
    assert result['status'] == 'clarify' and 'target' not in result


def test_history_never_silently_truncated():
    with pytest.raises(ValueError):
        payload_for_intent(['Texte'] * 9)


@pytest.mark.parametrize('prefix', ['peux-tu', 'tu peux', 'pourrais-tu', 'est-ce que tu peux',
                                   'je veux que tu', 'je voudrais que tu'])
@pytest.mark.parametrize('clitic', ['me', 'nous'])
def test_polite_request_supports_indirect_object_clitics(prefix, clitic):
    turns = [f'Alice, {prefix} {clitic} creer une note titre "Essai", texte "Demain".']
    assert validate_intent(plan('Essai', 'Demain'), turns)['status'] == 'ready'


@pytest.mark.parametrize('wording', [
    'Alice, peux-tu ne pas me creer une note',
    'Alice, pourrais-tu ne pas nous creer une note',
    'Alice, ne me cree pas une note',
    'Je ne veux pas que tu nous crees une note',
    'Explique la phrase "peux-tu me creer une note"',
    'Il a dit "tu peux nous creer une note"',
    '"Peux-tu me creer une note" est un exemple',
])
def test_clitic_support_does_not_authorize_negation_or_quoted_requests(wording):
    turns = [wording + ', titre "Essai", texte "Demain".']
    assert validate_intent(plan('Essai', 'Demain'), turns)['status'] == 'clarify'


def test_voice_exact_transcript_is_not_audio_truth_and_needs_review():
    source = ['Cree une note titre "Jardin", texte "Arroseur les fleurs".']
    validated = validate_intent(plan('Jardin', 'Arroseur les fleurs'), source)
    assert validated['status'] == 'ready'
    result = apply_input_policy(validated, 'voice')
    assert result['status'] == 'needs_confirmation'
    assert result['target'] == validated['target']
    assert 'Arroseur les fleurs' in result['question']
    result['target']['body'] = 'changed'
    assert validated['target']['body'] == 'Arroseur les fleurs'


def test_local_text_keeps_validated_ready_values():
    validated = validate_intent(plan('Essai', 'Demain'), ['Cree une note titre "Essai", texte "Demain".'])
    assert apply_input_policy(validated, 'local_text') == validated


@pytest.mark.parametrize('source', ['chat', 'page', 'ocr', 'confirmed_voice', None])
def test_unknown_input_source_cannot_authorize_action(source):
    result = apply_input_policy({'status': 'ready', 'target': {'title': 'x', 'body': 'y'}}, source)
    assert result['status'] == 'clarify' and 'target' not in result


@pytest.mark.parametrize('status', ['clarify', 'cancel'])
def test_voice_preserves_non_executable_decisions(status):
    value = {'status': status, 'reason': 'original'}
    assert apply_input_policy(value, 'voice') == value


def test_confirmation_policy_has_no_implicit_yes_bypass():
    result = apply_input_policy({'status': 'needs_confirmation', 'target': {'title': 'x', 'body': 'y'}}, 'local_text')
    assert result['status'] == 'clarify' and 'target' not in result


def test_unique_quote_is_grounded_in_actual_turn_despite_wrong_hint():
    turns = ['Cree une note.', 'Le titre est "Demain", le texte est "Arroser les plantes".']
    result = validate_intent(plan('Demain', 'Arroser les plantes'), turns)
    assert result['status'] == 'ready'
    assert result['sources']['title']['turn'] == 1
    assert result['sources']['title']['declared_turn'] == 0
    assert result['sources']['body']['turn'] == 1


def test_duplicate_quote_across_turns_is_not_resolved_by_model_hint():
    turns = ['Cree une note titre "Jardin", texte "Arroser les plantes".',
             'Je repete le titre "Jardin".']
    assert validate_intent(plan('Jardin', 'Arroser les plantes'), turns)['reason'] == 'citation_missing_or_ambiguous'


def test_wrong_hint_cannot_hide_superseded_actual_source():
    turns = ['Cree une note titre "Avant", texte "Demain".',
             'Finalement change le titre en "Apres".']
    result = validate_intent(plan('Avant', 'Demain', title_turn=1), turns)
    assert result['reason'] == 'citation_superseded_by_correction'


def test_global_quote_search_still_rejects_invalid_hint_type_and_range():
    turns = ['Cree une note.', 'Titre "Jardin", texte "Arroser".']
    for index in [True, -1, 2, '1']:
        assert validate_intent(plan('Jardin', 'Arroser', title_turn=index), turns)['reason'] == 'citation_schema'
