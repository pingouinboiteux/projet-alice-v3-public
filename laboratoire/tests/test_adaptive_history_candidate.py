"""Synthetic token counters; no model, database, or personal memory is opened."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from adaptive_history_candidate import install
from episodic_memory import Reader
from v5_context_memory import CarefulMemoryReader


def history_pairs(count):
    return [
        {'role': role, 'content': f'validation_history_{index}_{role}'}
        for index in range(count) for role in ('user', 'assistant')
    ]


def history_on_wire(messages):
    return [m for m in messages if m['content'].startswith('validation_history_')]


def harness(counter=None, sources=None):
    archives = copy.deepcopy(sources or [])
    store = SimpleNamespace(retrieve=lambda *a, **k: copy.deepcopy(archives), version=lambda: 1)
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


def test_import_does_not_install_and_explicit_restore_preserves_original():
    original = Reader.answer
    restore = install()
    assert Reader.answer is not original
    assert Reader.answer._baseline_source_sha256
    restore()
    assert Reader.answer is original


def test_long_history_is_preserved_when_native_schema_budget_fits(installed):
    history = history_pairs(10)
    before = copy.deepcopy(history)
    session, store = harness()
    CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
    wire = session.ask.call_args.args[0]
    assert history_on_wire(wire) == history
    assert wire[-1] == {'role': 'user', 'content': 'Question'}
    assert history == before
    session.count_tokens.assert_not_called()
    assert 'phenomenon' in session.count_response_tokens.call_args.args[1]['properties']


def test_native_schema_budget_discards_only_oldest_complete_pairs(installed):
    def counter(messages, schema):
        assert 'phenomenon' in schema['properties']
        return 5501 if len(history_on_wire(messages)) > 6 else 5500
    session, store = harness(counter)
    history = history_pairs(10)
    CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history)
    wire = session.ask.call_args.args[0]
    assert history_on_wire(wire) == history[-6:]
    assert wire[-1]['content'] == 'Question'
    assert session.count_response_tokens.call_args.args[0] == wire


def test_optional_documents_are_removed_before_any_history_pair(installed):
    def counter(messages, schema):
        return 5501 if 'validation_optional_document' in json.dumps(messages) else 5500
    session, store = harness(counter)
    history = history_pairs(8)
    CarefulMemoryReader(session, store, 'general_discussion').answer(
        'Question', history, auxiliary={'documents_publics': ['validation_optional_document']})
    wire = session.ask.call_args.args[0]
    assert history_on_wire(wire) == history
    assert 'validation_optional_document' not in json.dumps(wire)


def test_archives_discarded_by_general_route_never_consume_history_budget(installed):
    sources = [{'id': 'validation_source', 'date': '2026-01-01',
                'messages': [{'role': 'user', 'content': 'validation_archive_' * 1000}]}]
    before = copy.deepcopy(sources)
    session, store = harness(sources=sources)
    result = CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history_pairs(8))
    wire = session.ask.call_args.args[0]
    assert json.loads(wire[1]['content'].split(' : ', 1)[1])['archives'] == []
    assert result['sources'] == sources == before
    assert result['evidence_ids'] == [] and result['budget_omitted_sources'] == 0
    session.count_tokens.assert_not_called()


def test_oversized_fixed_prompt_refuses_before_generation(installed):
    session, store = harness(lambda messages, schema: 5501)
    with pytest.raises(ValueError, match='Final memory reply exceeds'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history_pairs(3))
    session.ask.assert_not_called()


@pytest.mark.parametrize('kind', ['specific_fact', 'general_preference'])
@pytest.mark.parametrize('final_eviction', [False, True])
def test_factual_routes_are_identical_with_and_without_candidate(kind, final_eviction):
    history = history_pairs(10)
    source = {'id': 'validation_source', 'date': '2026-01-01',
              'messages': [{'role': 'user', 'content': 'Contexte synthetique complet.'}]}
    sources = [source, dict(source, id='validation_lower_rank')] if final_eviction else [source]
    def count(messages, schema):
        shown = json.loads(messages[1]['content'].split(' : ', 1)[1])['archives']
        return 5501 if len(shown) > 1 else 100
    def run():
        session, store = harness(sources=sources, counter=count)
        with patch('episode_protocol._personal', return_value=(sources, {'requires_general_preference': True})), \
                patch('memory_source_provenance.resolve', side_effect=lambda session, sources, question: (sources, {'called': True})):
            result = CarefulMemoryReader(session, store, kind).answer('Question', history)
        return session.ask.call_args, result
    baseline = run()
    assert baseline[1]['budget_omitted_sources'] == int(final_eviction)
    restore = install()
    try:
        assert run() == baseline
    finally:
        restore()


@pytest.mark.parametrize('bad_history', [history_pairs(1)[:-1], [
    {'role': 'assistant', 'content': 'validation_history_orphan'},
    {'role': 'user', 'content': 'validation_history_orphan'},
]])
def test_malformed_history_is_not_silently_split(installed, bad_history):
    session, store = harness()
    with pytest.raises(ValueError, match='complete user/assistant pairs'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', bad_history)
    session.ask.assert_not_called()


def test_candidate_requires_counter_including_native_schema(installed):
    session, store = harness()
    del session.count_response_tokens
    with pytest.raises(ValueError, match='native schema token counting'):
        CarefulMemoryReader(session, store, 'general_discussion').answer('Question', history_pairs(2))
    session.ask.assert_not_called()
