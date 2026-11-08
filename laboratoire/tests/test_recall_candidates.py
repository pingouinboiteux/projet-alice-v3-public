"""Synthetic independent checks of the process-local recall ablations."""
import copy
import shutil
from unittest.mock import patch

import pytest

import episode_protocol
import memory_recall_candidates
import reviewed_memory_reader
from v5_context_memory import V5Reader
from episodic_memory import Reader
from memory_recall_candidates import candidate, deduplicated_answer
from test_memory_final_budget import payload, setup_reader, sources


def test_dedup_preserves_sources_and_only_removes_duplicate_payload_field():
    archives = sources()
    archives[0]['messages'].append({'role': 'assistant', 'content': 'Une question ?'})
    before = copy.deepcopy(archives)
    reader, session = setup_reader(archives, lambda *args: 100, query_kind='specific_fact')
    original = Reader.answer
    with candidate('baseline'):
        reader.answer('Que sais-tu ?')
    baseline = payload(session.ask.call_args.args[0])['archives']
    with candidate('dedup'):
        with patch('builtins.open', side_effect=AssertionError('Unexpected file access')):
            reader.answer('Que sais-tu ?')
        shown = payload(session.ask.call_args.args[0])['archives']
        expected = [{key: value for key, value in source.items()
                     if key != 'paroles_de_la_personne'} for source in baseline]
        assert shown == expected
        assert archives == before
    assert Reader.answer is original


@pytest.mark.parametrize('variant', ['baseline', 'dedup', 'combined_dedup', 'precise_priority'])
def test_restore_exact_function_and_protocol_after_failure(variant):
    original = Reader.answer
    reviewed = reviewed_memory_reader.ReviewedReader.answer
    roles = episode_protocol.SOURCE_ROLES
    with pytest.raises(ValueError, match='synthetic failure'):
        with candidate(variant):
            assert Reader.answer is not original
            raise ValueError('synthetic failure')
    assert Reader.answer is original
    assert reviewed_memory_reader.ReviewedReader.answer is reviewed
    assert episode_protocol.SOURCE_ROLES is roles


@pytest.mark.parametrize('source', [
    'def answer(self):\n    return None\n',
    'def answer(self):\n    def archives_for(sources):\n        return []\n',
])
def test_missing_target_fails_before_install(source):
    original = Reader.answer
    with pytest.raises(ValueError):
        deduplicated_answer(source)
    assert Reader.answer is original


def test_preference_protocol_gets_identical_message_inputs():
    archives = sources()
    reader, _ = setup_reader(archives, lambda *args: 100, query_kind='general_preference')
    received = []
    def personal(session, view, question):
        received.append(episode_protocol.evidence_messages(view, question))
        return view, {'requires_general_preference': True}
    with patch('episode_protocol._personal', side_effect=personal):
        with candidate('baseline'):
            reader.answer('Quelle preference ?')
        with candidate('dedup'):
            reader.answer('Quelle preference ?')
    assert received[0] == received[1]


def test_installed_is_native_even_when_historical_bundle_unavailable(tmp_path):
    original = Reader.answer
    reviewed = reviewed_memory_reader.ReviewedReader.answer
    roles = episode_protocol.SOURCE_ROLES
    candidates = V5Reader.candidate_sources
    selected = reviewed_memory_reader.Selected.__init__
    ask = reviewed_memory_reader.ask
    with patch.object(memory_recall_candidates, 'BASELINE_DIR', tmp_path):
        with pytest.raises(RuntimeError, match='synthetic failure'):
            with candidate('installed'):
                assert Reader.answer is original
                assert reviewed_memory_reader.ReviewedReader.answer is reviewed
                assert episode_protocol.SOURCE_ROLES is roles
                assert V5Reader.candidate_sources is candidates
                assert reviewed_memory_reader.Selected.__init__ is selected
                assert reviewed_memory_reader.ask is ask
                raise RuntimeError('synthetic failure')
    assert Reader.answer is original
    assert reviewed_memory_reader.ReviewedReader.answer is reviewed


def test_installed_rejects_non_native_ranking():
    with pytest.raises(ValueError, match='native selection'):
        with candidate('installed', frozen_ranking={'kind': 'specific_fact', 'ids': []}):
            pytest.fail('Override accepted')


@pytest.mark.parametrize('filename', ['Reader.answer.py.txt', 'ReviewedReader.answer.py.txt', 'roles.txt'])
def test_corrupted_fixture_fails_before_any_patch(tmp_path, filename):
    shutil.copytree(memory_recall_candidates.BASELINE_DIR, tmp_path / 'baseline')
    (tmp_path / 'baseline' / filename).write_bytes(b'corrupted')
    original = Reader.answer
    reviewed = reviewed_memory_reader.ReviewedReader.answer
    roles = episode_protocol.SOURCE_ROLES
    with patch.object(memory_recall_candidates, 'BASELINE_DIR', tmp_path / 'baseline'):
        with pytest.raises(ValueError, match='hash mismatch'):
            with candidate('baseline'):
                pytest.fail('Corrupted baseline accepted')
    assert Reader.answer is original
    assert reviewed_memory_reader.ReviewedReader.answer is reviewed
    assert episode_protocol.SOURCE_ROLES is roles


def test_baseline_ignores_installed_roles_and_uses_original_module_globals():
    original = Reader.answer
    reviewed = reviewed_memory_reader.ReviewedReader.answer
    frozen_roles = memory_recall_candidates._baseline()['roles.txt']
    with patch.object(episode_protocol, 'SOURCE_ROLES', 'installed sentinel'):
        with candidate('baseline'):
            assert episode_protocol.SOURCE_ROLES == frozen_roles
            assert Reader.answer.__globals__ is original.__globals__
            assert reviewed_memory_reader.ReviewedReader.answer.__globals__ is reviewed.__globals__
        assert episode_protocol.SOURCE_ROLES == 'installed sentinel'
