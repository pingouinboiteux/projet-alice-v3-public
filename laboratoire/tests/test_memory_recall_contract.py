"""Historical checks of the REJECTED precise_dedup experiment.

Deduplication regressed real recall cases 12/14 and must not be activated.
These mechanical checks are not a production contract or model qualification.
Synthetic counters check fitting mechanics, not real tokenizer/model quality.
"""
import copy
from unittest.mock import patch

import pytest

import episode_protocol
from memory_recall_candidates import candidate
from test_memory_final_budget import payload, setup_reader


@pytest.fixture
def recall_contract():
    # Historical rejected candidate only; never replace this with production.
    with candidate('precise_dedup'):
        yield


def archives():
    return [
        {'id': 'validation_ranked', 'date': '2026-01-02', 'messages': [
            {'role': 'user', 'content': 'Je cite Luc : "Vous restez ici."'},
            {'role': 'assistant', 'content': 'Je proposais de partir.'}]},
        {'id': 'validation_witness', 'date': '2026-01-01', 'messages': [
            {'role': 'user', 'content': 'Je reste uniquement pour cette occasion.'}]},
    ]


def test_complete_archive_messages_and_quotes_reach_final_context_once(recall_contract):
    source = archives()
    before = copy.deepcopy(source)
    reader, session = setup_reader(source, lambda *args: 100,
                                   query_kind='specific_fact', memory_reasoning=True)
    # Isolate serialization from the separately tested LLM provenance decision.
    with patch('memory_source_provenance.resolve', side_effect=lambda session, view, question:
               (copy.deepcopy(view), {'called': False, 'hidden_assistant_turns': 0})):
        result = reader.answer('Que disais-je et que proposais-tu ?')
    messages = session.ask_memory.call_args.args[0]
    shown = payload(messages)['archives']
    assert shown == sorted(before, key=lambda item: (item['date'], item['id']))
    assert source == before
    assert result['admitted_ids'] == ['validation_witness', 'validation_ranked']
    # The actual contract reaches the factual call, without a persona overriding it.
    assert episode_protocol.SOURCE_ROLES in messages[0]['content']
    assert all(set(item) == {'id', 'date', 'messages'} for item in shown)


def test_duplicate_space_freed_keeps_tail_witness_without_reranking(recall_contract):
    source = [{'id': identity, 'date': date, 'messages': [
        {'role': 'user', 'content': text * 1200}]} for identity, date, text in [
            ('validation_ranked_one', '2026-01-03', 'a'),
            ('validation_ranked_two', '2026-01-02', 'b'),
            ('validation_witness', '2026-01-01', 'c')]]
    before = copy.deepcopy(source)
    scale = [1]

    def measure(messages):
        # Deliberately charge each serialized text occurrence. Old duplicated
        # archives cost 7200 units, complete unduplicated archives cost 3600.
        data = payload(messages)
        return 500 + scale[0] * sum(
            sum(len(turn['content']) for turn in item['messages'])
            + len(item.get('paroles_de_la_personne', ''))
            for item in data['archives'])

    reader, session = setup_reader(source, lambda messages, schema: measure(messages),
                                   query_kind='specific_fact', memory_reasoning=True)
    session.count_tokens.side_effect = lambda messages: (
        measure(messages) if messages[1]['content'].startswith('Archives historiques') else 100)
    result = reader.answer('Quel souvenir ?')
    shown = payload(session.ask_memory.call_args.args[0])['archives']
    assert {item['id'] for item in shown} == {item['id'] for item in before}
    assert result['budget_omitted_sources'] == 0
    assert source == before
    assert measure(session.ask_memory.call_args.args[0]) == 4100
    # Under tighter capacity the original tail still goes first: deduplication
    # does not silently prioritize the witness over the reranker's sources.
    scale[0] = 2
    result = reader.answer('Quel souvenir ?')
    assert result['admitted_ids'] == ['validation_ranked_two', 'validation_ranked_one']
    assert result['budget_omitted_sources'] == 1
    assert source == before


def test_rejected_preference_keeps_complete_context_without_proof(recall_contract):
    source = [archives()[1]]
    reader, session = setup_reader(source, lambda *args: 100,
                                   query_kind='general_preference', memory_reasoning=True)
    with patch('episode_protocol._personal', return_value=([], {'requires_general_preference': True})):
        result = reader.answer('Quelle est mon habitude ?')
    data = payload(session.ask.call_args.args[0])
    assert data['archives'] == []
    assert data['contexte_non_probant'] == source
    assert result['admitted_ids'] == []
    session.ask_memory.assert_not_called()
