"""Synthetic retrieval and native-schema counters; no real memory or model."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from adaptive_context_candidate import install
from episodic_memory import Reader
from v5_context_memory import CarefulMemoryReader


def pairs(count):
    return [{'role': role, 'content': f'validation_history_{i}_{role}'}
            for i in range(count) for role in ('user', 'assistant')]


def source(identity, messages=None):
    return {'id': identity, 'date': '2026-01-01',
            'messages': messages or [{'role': 'user', 'content': 'Hypothese limitee au cas fictif.'},
                                     {'role': 'assistant', 'content': 'Affirmation ancienne, pas preuve.'}]}


def payload(messages):
    return json.loads(messages[1]['content'].split(' : ', 1)[1])


def archived_words(sources):
    return [dict(item, paroles_de_la_personne=' '.join(
        m['content'] for m in item['messages'] if m['role'] == 'user'))
        for item in sorted(sources, key=lambda item: (item['date'], item['id']))]


def harness(sources=(), counter=None, current=None):
    store = SimpleNamespace(retrieve=lambda *a, **k: copy.deepcopy(sources), version=lambda: 1,
                            current_episode_id=current)
    session = SimpleNamespace(
        ask=Mock(return_value=('{"reply":"Texte","evidence_ids":[]}', 0, {})),
        count_tokens=Mock(return_value=1),
        count_response_tokens=Mock(side_effect=counter or (lambda messages, schema: 1)),
    )
    return session, store


@pytest.fixture
def installed():
    original = Reader.answer
    restore = install()
    try:
        yield
    finally:
        restore()
        assert Reader.answer is original


def test_import_does_not_install_and_restore_is_exact():
    original = Reader.answer
    restore = install()
    assert Reader.answer is not original and Reader.answer._baseline_source_sha256
    restore()
    assert Reader.answer is original


def test_retrieved_words_are_context_only_and_history_stays_twelve_messages(installed):
    sources = [source('validation_old')]
    before = copy.deepcopy(sources)
    history = pairs(10)
    session, store = harness(sources)
    result = CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
    wire = session.ask.call_args.args[0]
    assert payload(wire)['archives'] == []
    assert payload(wire)['paroles_passees_non_preuves'] == archived_words(sources)
    assert wire[2:-1] == history[-12:] and wire[-1]['content'] == 'Question'
    assert result['evidence_ids'] == result['admitted_ids'] == []
    assert result['sources'] == sources == before
    assert result['conversation_context_omitted'] == 0
    session.count_tokens.assert_not_called()


def test_current_archive_already_in_history_leaves_generation_exactly_unchanged():
    history = pairs(3)
    sources = [source('validation_current', history)]
    def run():
        session, store = harness(sources, current='validation_current')
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
        return session.ask.call_args
    baseline = run()
    restore = install()
    try:
        assert run() == baseline
        assert 'paroles_passees_non_preuves' not in payload(run().args[0])
    finally:
        restore()


def test_partial_overlap_keeps_complete_context_and_scope(installed):
    history = pairs(10)
    sources = [source('validation_current', history)]
    session, store = harness(sources, current='validation_current')
    CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
    assert payload(session.ask.call_args.args[0])['paroles_passees_non_preuves'] == archived_words(sources)


def test_schema_budget_evicts_whole_lowest_ranked_archive_without_trimming_history(installed):
    sources = [source('validation_first'), source('validation_second')]
    before = copy.deepcopy(sources)
    def counter(messages, schema):
        assert 'phenomenon' in schema['properties']
        return 5501 if len(payload(messages).get('paroles_passees_non_preuves', [])) > 1 else 5500
    session, store = harness(sources, counter)
    history = pairs(8)
    result = CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
    wire = session.ask.call_args.args[0]
    assert payload(wire)['paroles_passees_non_preuves'] == archived_words(sources[:1])
    assert wire[2:-1] == history[-12:]
    assert result['sources'] == sources == before
    assert result['conversation_context_omitted'] == 1


def test_optional_document_removed_before_retrieved_context(installed):
    sources = [source('validation_source')]
    def counter(messages, schema):
        return 5501 if 'validation_optional_document' in json.dumps(messages) else 5500
    session, store = harness(sources, counter)
    result = CarefulMemoryReader(session, store, 'general_discussion').answer(
        'Question', pairs(3), auxiliary={'documents_publics': ['validation_optional_document']})
    assert payload(session.ask.call_args.args[0])['paroles_passees_non_preuves'] == archived_words(sources)
    assert result['conversation_context_omitted'] == 0


def test_eviction_removes_empty_context_key(installed):
    def counter(messages, schema):
        return 5501 if 'paroles_passees_non_preuves' in payload(messages) else 5500
    session, store = harness([source('validation_source')], counter)
    result = CarefulMemoryReader(session, store, 'general_discussion').answer('Question', pairs(3))
    assert 'paroles_passees_non_preuves' not in payload(session.ask.call_args.args[0])
    assert result['conversation_context_omitted'] == 1


def test_oversized_fixed_input_refuses_without_generation(installed):
    session, store = harness([source('validation_source')], lambda messages, schema: 5501)
    with pytest.raises(ValueError, match='Final memory reply exceeds'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', pairs(3))
    session.ask.assert_not_called()


@pytest.mark.parametrize('kind', ['specific_fact', 'general_preference'])
@pytest.mark.parametrize('final_eviction', [False, True])
def test_factual_routes_preserve_exact_requests_and_result(kind, final_eviction):
    sources = [source('validation_source')]
    if final_eviction:sources.append(source('validation_lower_rank'))
    def count(messages, schema):
        return 5501 if len(payload(messages)['archives']) > 1 else 100
    def run():
        session, store = harness(sources, count)
        with patch('episode_protocol._personal', return_value=(sources, {'requires_general_preference': True})), \
                patch('memory_source_provenance.resolve', side_effect=lambda session, sources, question: (sources, {'called': True})):
            result = CarefulMemoryReader(session, store, kind).answer('Question', pairs(9))
        return session.ask.call_args, result
    baseline = run()
    assert baseline[1]['budget_omitted_sources'] == int(final_eviction)
    restore = install()
    try:
        assert run() == baseline
    finally:
        restore()


def test_context_cannot_be_cited_as_admitted_proof(installed):
    session, store = harness([source('validation_source')])
    session.ask.return_value = ('{"reply":"Texte","evidence_ids":["validation_source"]}', 0, {})
    with pytest.raises(ValueError, match='unsupported source reference'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', pairs(3))


def test_native_schema_counter_is_required(installed):
    session, store = harness()
    del session.count_response_tokens
    with pytest.raises(ValueError, match='native schema token counting'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', pairs(2))
    session.ask.assert_not_called()
