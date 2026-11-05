"""Behavioral retrieval/budget checks with synthetic sources and no database."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from episodic_memory import Reader
from reviewed_memory_reader import ReviewedReader, Selected


def source(identity, date, text):
    return {'id': 'validation_' + identity, 'date': date,
            'messages': [{'role': 'user', 'content': text}],
            'search_excerpt': text[:20]}


class ReadOnlyStore:
    """Fail if tested code attempts any database mutation or unexpected query."""
    def __init__(self, sources, recent=()):
        self.sources = copy.deepcopy(sources)
        self.recent = list(recent)
        self.db = self
        self.queries = []

    def execute(self, query):
        self.queries.append(query)
        if query == 'SELECT 1 FROM episodes LIMIT 1':
            return SimpleNamespace(fetchone=lambda: (1,))
        if query == 'SELECT id FROM episodes ORDER BY date DESC,id DESC LIMIT 2':
            return [(identity,) for identity in self.recent]
        raise AssertionError('Unexpected database access: ' + query)

    def candidates(self, question):
        return copy.deepcopy(self.sources)

    def get(self, identity):
        return copy.deepcopy(next(item for item in self.sources if item['id'] == identity))

    def version(self):
        return 7


def archives(messages):
    return json.loads(messages[1]['content'].split(' : ', 1)[1])['archives']


def budget_session(limit):
    delivered = []

    def ask(messages, response_schema):
        delivered.append(copy.deepcopy(archives(messages)))
        ids = [item['id'] for item in delivered[-1]]
        return json.dumps({'reply': 'Reponse fictive.', 'evidence_ids': ids}), 0, {}

    return SimpleNamespace(ask=ask, delivered=delivered, count_tokens=lambda messages: 100,
        count_response_tokens=lambda messages, schema: 5501 if len(archives(messages)) > limit else 100)


class WitnessReader(ReviewedReader):
    retained_retrieval = 2


def reviewed(store, ranked, limit=20, kind='specific_fact', reader_type=WitnessReader):
    session = budget_session(limit)
    with patch('reviewed_memory_reader.ask', return_value={'kind': kind, 'ids': ranked}):
        result = reader_type(session, store).answer('Question fictive ?')
    return result, session


def test_independent_retrieval_witness_survives_budget_that_used_to_discard_it():
    witness = source('voice', '2026-01-01', 'La discussion a commence par un test de voix.')
    second = source('second', '2026-01-02', 'Un autre souvenir.')
    distractor = source('distractor', '2026-01-03', 'Une discussion privee distincte.')
    other = source('other', '2026-01-04', 'Encore une autre discussion.')
    store = ReadOnlyStore([witness, second, distractor, other])
    before = copy.deepcopy(store.sources)
    result, session = reviewed(store, [distractor['id'], other['id']], limit=2)
    assert next(item for item in session.delivered[-1] if item['id'] == witness['id'])['messages'] == witness['messages']
    assert distractor['id'] in result['admitted_ids']
    assert other['id'] not in result['admitted_ids']
    # Compare the actual budget reader on the former append-after-reranking order.
    old_session = budget_session(2)
    old = Reader(old_session, Selected(store, [distractor, other, witness, second]),
                 query_kind='specific_fact').answer('Question fictive ?')
    assert witness['id'] not in old['admitted_ids']
    assert store.sources == before and store.version() == 7


def test_recent_ranked_correction_remains_complete_when_three_sources_fit():
    old = source('old', '2026-01-01', 'Mon rendez-vous est mardi.')
    second = source('context', '2026-01-02', 'Nous parlions du rendez-vous.')
    correction = source('correction', '2026-01-03',
        'Correction : le rendez-vous est jeudi. Mardi est annule, ne conserve pas cette ancienne date.')
    store = ReadOnlyStore([old, second, correction], recent=[correction['id'], second['id']])
    before = copy.deepcopy(store.sources)
    result, session = reviewed(store, [correction['id'], correction['id']], limit=3)
    shown = session.delivered[-1]
    assert shown[-1]['messages'] == correction['messages']
    assert [item['id'] for item in shown] == [old['id'], second['id'], correction['id']]
    assert len(result['admitted_ids']) == len(set(result['admitted_ids']))
    assert store.sources == before


def test_two_source_budget_keeps_first_witness_and_first_ranked_correction():
    old = source('old', '2026-01-01', 'Mon rendez-vous est mardi.')
    second = source('context', '2026-01-02', 'Contexte ancien du rendez-vous.')
    correction = source('correction', '2026-01-03', 'Correction : jeudi, et non mardi.')
    store = ReadOnlyStore([old, second, correction])
    result, session = reviewed(store, [correction['id']], limit=2)
    assert result['admitted_ids'] == [old['id'], correction['id']]
    assert result['budget_omitted_sources'] == 1
    assert session.delivered[-1][-1]['messages'] == correction['messages']
    assert all(item['messages'] == store.get(item['id'])['messages'] for item in session.delivered[-1])


class CaptureReader:
    def __init__(self, session, episodes, query_kind=None):
        self.episodes = episodes

    def answer(self, *args):
        return {'sources': self.episodes.retrieve()}


@pytest.mark.parametrize('kind,retained', [('general_discussion', 2), ('specific_fact', 0)])
def test_unaffected_modes_preserve_reranker_then_recency_order(kind, retained):
    first = source('first', '2026-01-01', 'Premier souvenir.')
    second = source('second', '2026-01-02', 'Deuxieme souvenir.')
    ranked = source('ranked', '2026-01-03', 'Source choisie par classement.')
    store = ReadOnlyStore([first, second, ranked], recent=[second['id'], ranked['id']])
    reader_type = type('CaptureReviewed', (ReviewedReader,),
                       {'retained_retrieval': retained, 'reader_type': CaptureReader})
    result, _ = reviewed(store, [ranked['id'], ranked['id']], kind=kind, reader_type=reader_type)
    expected = [ranked['id'], first['id'], second['id']] if retained else [ranked['id'], second['id']]
    assert [item['id'] for item in result['sources']] == expected
