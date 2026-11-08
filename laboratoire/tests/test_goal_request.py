"""Fictitious local turns and model replies, with no network or private state."""
import json
from unittest.mock import Mock
import pytest
from goal_request import can_handle_goal, is_goal_followup, interpret_goal

URL = 'https://example.org/'
TEXT = 'Trouve les horaires sur https://example.org/'
TARGET = {'url': URL, 'question': 'les horaires'}


def session(values=None, turns=None, decision='execute'):
    values = TARGET if values is None else values
    turns = turns or {}
    reply = {'intent': 'execute', **{k: {'turn': turns.get(k, 0), 'quote': v}
                                    for k, v in values.items()}}
    s = Mock()
    s.ask.side_effect = [(json.dumps(reply), 0, {}),
                         (json.dumps({'decision': decision}), 0, {})]
    return s


@pytest.mark.parametrize('text', [TEXT,
    'Cherche sur https://example.org/ le prix adulte',
    'Peux-tu trouver les horaires sur https://example.org/',
    'Alice, recherche le tarif sur https://example.org/',
    'Sur https://example.org/, trouve les horaires',
    'Trouve le prix sur ce site', '/chercher ' + URL + ' | les horaires'])
def test_candidate(text):
    assert can_handle_goal(text)


@pytest.mark.parametrize('text', [None, 'Bonjour', 'Cherche mes notes',
    'Par exemple ' + TEXT, 'Il a dit ' + TEXT, 'Si je dis ' + TEXT,
    '"' + TEXT + '"', 'Ne cherche pas les horaires sur ' + URL,
    'Comment chercher sur ' + URL, 'Trouve "les horaires sur ' + URL,
    '/chercherailleurs ' + URL])
def test_nonrequest(text):
    assert not can_handle_goal(text)
    assert interpret_goal(session(), [text], 'text')['status'] != 'ready'


@pytest.mark.parametrize('text', ['La question est le prix adulte',
    'Finalement la page est ' + URL, 'Remplace la recherche par les horaires',
    'stop', 'annule'])
def test_followup(text):
    assert is_goal_followup(text)


@pytest.mark.parametrize('text', ['Bonjour', 'oui', '"stop"',
    'Il a dit la page est ' + URL])
def test_not_followup(text):
    assert not is_goal_followup(text)


def test_exact_target_and_originals_in_intent_check():
    s = session()
    result = interpret_goal(s, [TEXT], 'voice')
    assert result['status'] == 'ready'
    assert result['target'] == TARGET
    for field, ref in result['sources'].items():
        assert TEXT[ref['start']:ref['end']] == TARGET[field]
    data = json.loads(s.ask.call_args_list[1].args[0][1]['content'])
    assert data == {'tours_locaux': [TEXT], 'extraction_a_verifier': TARGET}


def test_command_without_model():
    s = session()
    assert interpret_goal(s, ['/chercher ' + URL + ' | les horaires'], 'text') == {
        'status': 'ready', 'target': TARGET}
    s.ask.assert_not_called()


@pytest.mark.parametrize('text', ['/chercher', '/chercher ' + URL,
    '/chercher ' + URL + ' | ', '/chercher ' + URL + ' | prix | autre',
    '/chercher https://127.0.0.1/ | prix', '/chercher https://a.local/ | prix',
    '/chercher https://user:secret@example.org/ | prix',
    '/chercher http://example.org/ | prix'])
def test_invalid_command(text):
    s = session()
    assert interpret_goal(s, [text], 'text')['status'] == 'clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('source', ['twitch', 'discord', 'page', None])
def test_local_only(source):
    s = session()
    assert interpret_goal(s, [TEXT], source)['status'] == 'clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('turns', [[], [TEXT]*9, [TEXT + 'x'*16000], [TEXT, {}]])
def test_history_bounds(turns):
    s = session()
    assert interpret_goal(s, turns, 'text')['status'] == 'clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('values', [dict(TARGET, url='https://invented.org/'),
    dict(TARGET, url='https://example.org'), dict(TARGET, question='prix adulte'),
    dict(TARGET, question=TEXT)])
def test_invented_partial_or_overlapping_fields(values):
    assert interpret_goal(session(values), [TEXT], 'text')['status'] == 'clarify'


def test_repeated_quote_not_bound_arbitrarily():
    assert interpret_goal(session(), [TEXT + ' les horaires'], 'text')['status'] == 'clarify'


def test_multiple_sites_not_selected_by_model():
    s = session()
    assert interpret_goal(s, [TEXT + ' et https://other.org/'], 'text')['status'] == 'clarify'
    s.ask.assert_not_called()


def test_corrections_keep_independent_latest_fields():
    texts = [TEXT, 'La page est https://example.org/new', 'La question est le prix adulte']
    target = {'url': 'https://example.org/new', 'question': 'le prix adulte'}
    result = interpret_goal(session(target, {'url': 1, 'question': 2}), texts, 'text')
    assert result['status'] == 'ready' and result['target'] == target
    assert result['sources']['url']['turn'] == 1
    assert result['sources']['question']['turn'] == 2


def test_stale_question_is_rejected():
    texts = [TEXT, 'La question est le prix adulte']
    assert interpret_goal(session(), texts, 'text')['reason'] == 'superseded_question'


def test_url_correction_resolves_unique_explicit_value():
    texts = [TEXT, 'La page est https://example.org/new']
    result = interpret_goal(session(), texts, 'text')
    assert result['target']['url'] == 'https://example.org/new'


def test_cancellation_and_unrelated_followup():
    s = session()
    assert interpret_goal(s, [TEXT, 'annule'], 'text')['status'] == 'cancel'
    assert interpret_goal(s, [TEXT, 'Bonjour'], 'text')['status'] == 'clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('tail', [' demain', ' si je termine ma partie', ' mais attends'])
def test_deferred_outside_question(tail):
    s = session()
    assert interpret_goal(s, [TEXT + tail], 'text')['status'] == 'clarify'
    assert s.ask.call_count == 1


@pytest.mark.parametrize('decision', ['clarify', 'discuss'])
def test_condition_hidden_in_question_still_checks_original(decision):
    question = 'les horaires si je termine ma partie'
    text = 'Trouve sur ' + URL + ' ' + question
    s = session(dict(TARGET, question=question), decision=decision)
    assert interpret_goal(s, [text], 'text')['status'] == decision
    assert json.loads(s.ask.call_args.args[0][1]['content'])['tours_locaux'] == [text]


def test_legitimate_condition_in_question():
    text = 'Trouve sur ' + URL + ' le tarif si je suis mineur'
    s = session(dict(TARGET, question='le tarif si je suis mineur'))
    assert interpret_goal(s, [text], 'text')['status'] == 'ready'


@pytest.mark.parametrize('raw', ['not json', '{}', '{"intent":"execute"}',
    '{"intent":"discuss","url":"invented"}', '{"intent":"execute","intent":"discuss"}'])
def test_bad_extraction(raw):
    s = Mock(ask=Mock(return_value=(raw, 0, {})))
    assert interpret_goal(s, [TEXT], 'text')['status'] == 'clarify'


@pytest.mark.parametrize('intent', ['clarify', 'discuss', 'cancel'])
def test_extraction_status(intent):
    s = Mock(ask=Mock(return_value=(json.dumps({'intent': intent}), 0, {})))
    assert interpret_goal(s, [TEXT], 'text')['status'] == intent


def test_bad_intent_check():
    s = session()
    s.ask.side_effect = [(json.dumps({'intent': 'execute', **{
        k: {'turn': 0, 'quote': v} for k, v in TARGET.items()}}), 0, {}), ('{}', 0, {})]
    assert interpret_goal(s, [TEXT], 'text')['status'] == 'clarify'
def test_named_link_keeps_priority_over_search_word_in_its_question():
    from goal_request import can_handle_goal
    from link_request import can_handle_link
    text='Sur https://example.org, suis le lien Tarifs et cherche le prix adulte.'
    assert can_handle_link(text)
    assert not can_handle_goal(text)
