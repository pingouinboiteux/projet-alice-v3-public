"""Search orchestration with synthetic providers/readers/models only."""
import copy
import json
from unittest.mock import Mock

import pytest

from public_web_search import read_search


ITEMS = [{'id': 'S' + str(i), 'title': 'Source ' + str(i),
          'url': 'https://source' + str(i) + '.org/'} for i in range(1, 5)]


class Harness:
    def __init__(self, responses=None):
        self.items = copy.deepcopy(ITEMS[:3])
        self.responses = iter(responses or [{'ids': ['S1', 'S2', 'S3']},
                                           {'relation': 'consistent'}])
        self.session = Mock()
        self.session.ask.side_effect = self.ask
        self.now = 0
        self.stopped = False
        self.provider = Mock(side_effect=self.provide)
        self.reader = Mock(side_effect=self.read)
        self.pages = {}

    def ask(self, messages, **kwargs):
        response = next(self.responses)
        if callable(response):
            response = response(messages, kwargs)
        return (response if isinstance(response, str) else json.dumps(response)), 0, {}

    def provide(self, question, check, **kwargs):
        check()
        return self.items

    def read(self, session, url, question, **kwargs):
        kwargs['cancelled']()
        page = self.pages.get(url, {'status': 'found', 'url': url,
                              'evidence': ['Tarif : 17 euros.'], 'visited': [url],
                              'reply': 'UNTRUSTED READER PROSE'})
        if isinstance(page, Exception):
            raise page
        if callable(page):
            return page()
        return page

    def run(self, **kwargs):
        return read_search(self.session, 'Quel tarif ?', provider=self.provider,
                           reader=self.reader, clock=lambda: self.now,
                           cancelled=lambda: self.stopped, **kwargs)


def test_three_sources_read_two_pages_each_and_render_only_structured_evidence():
    h = Harness()
    result = h.run(source='voice')
    assert result['status'] == 'found'
    assert result['sources'] == [x['url'] for x in h.items]
    assert len(result['evidence']) == 3
    assert result['partial'] is True
    assert 'UNTRUSTED READER PROSE' not in result['reply']
    assert result['reply'].count('Tarif : 17 euros.') == 3
    for call in h.reader.call_args_list:
        assert call.kwargs['max_pages'] == 2
        assert call.kwargs['source'] == 'voice'
    compared = json.loads(h.session.ask.call_args_list[-1].args[0][1]['content'])
    assert compared['citations'] == result['evidence']
    assert h.provider.call_args.kwargs['deadline'] == 120


@pytest.mark.parametrize('raw', [
    {'ids': ['S9']}, {'ids': ['https://evil.org/']}, {'ids': ['S1', 'S1']},
    {'ids': ['S1', 'S2', 'S3', 'S4']}, {'ids': [True]}, {'ids': 'S1'},
    {'ids': ['S1'], 'extra': True}, [], 'not json', '{"ids":["S1"],"ids":[]}',
])
def test_invalid_model_selection_never_reaches_reader(raw):
    h = Harness([raw])
    with pytest.raises(ValueError):
        h.run()
    h.reader.assert_not_called()


def test_same_origin_selected_twice_is_read_once():
    h = Harness([{'ids': ['S1', 'S2', 'S3']}, {'relation': 'consistent'}])
    h.items[1]['url'] = 'https://SOURCE1.org./other'
    result = h.run()
    assert result['sources'] == [ITEMS[0]['url'], ITEMS[2]['url']]
    assert h.reader.call_count == 2


@pytest.mark.parametrize('items', [[], None, ITEMS * 3,
    [dict(ITEMS[0], snippet='UNVERIFIED ANSWER')], [ITEMS[0], ITEMS[0]],
    [dict(ITEMS[0], url='http://example.org/')], [dict(ITEMS[0], url='https://127.0.0.1/')]])
def test_invalid_or_empty_inventory_never_reaches_reader(items):
    h = Harness()
    h.items = items
    if items == []:
        assert h.run()['status'] == 'missing'
    else:
        with pytest.raises(ValueError):
            h.run()
    h.reader.assert_not_called()
    h.session.ask.assert_not_called()


def test_empty_selection_never_turns_search_title_into_evidence():
    h = Harness([{'ids': []}])
    h.items[0]['title'] = 'UNVERIFIED ANSWER'
    result = h.run()
    assert result['status'] == 'missing'
    assert 'UNVERIFIED ANSWER' not in result['reply']
    h.reader.assert_not_called()


@pytest.mark.parametrize('relation,status', [('consistent', 'found'),
    ('conflicting', 'ambiguous'), ('inconclusive', 'ambiguous')])
def test_relation_controls_caution_without_adding_model_prose(relation, status):
    h = Harness([{'ids': ['S1', 'S2']}, {'relation': relation}])
    h.pages[ITEMS[1]['url']] = {'status': 'found', 'url': ITEMS[1]['url'],
                               'evidence': ['Tarif : 19 euros.']}
    result = h.run()
    assert result['status'] == status
    assert '17 euros' in result['reply'] and '19 euros' in result['reply']


@pytest.mark.parametrize('raw', ['not json', {'relation': 'invented'},
    {'relation': 'consistent', 'answer': 'INVENTED ANSWER'}, [],
    '{"relation":"consistent","relation":"conflicting"}'])
def test_invalid_comparison_is_inconclusive_and_keeps_quotes(raw):
    h = Harness([{'ids': ['S1', 'S2']}, raw])
    result = h.run()
    assert result['status'] == 'ambiguous'
    assert result['relation'] == 'inconclusive'
    assert 'INVENTED ANSWER' not in result['reply']


def test_single_source_has_explicit_uncorroborated_warning_and_no_comparison():
    h = Harness([{'ids': ['S1']}])
    result = h.run()
    assert result['relation'] == 'single'
    assert 'seule source' in result['reply'] and 'pas recoupe' in result['reply']
    assert h.session.ask.call_count == 1


def test_internal_source_ambiguity_cannot_be_overruled_by_comparator():
    h = Harness()
    h.pages[ITEMS[0]['url']] = {'status': 'ambiguous', 'url': ITEMS[0]['url'],
                               'evidence': ['Tarif : 17 euros.', 'Tarif : 19 euros.']}
    assert h.run()['status'] == 'ambiguous'


@pytest.mark.parametrize('page', [ValueError('blocked'), OSError('unavailable'),
    {'status': 'missing', 'reply': 'UNVERIFIED ANSWER'},
    {'status': 'found', 'url': ITEMS[0]['url'], 'evidence': []},
    {'status': 'found', 'url': ITEMS[0]['url'], 'evidence': ['x' * 501]},
    {'status': 'found', 'url': 'https://other.org/', 'evidence': ['UNVERIFIED ANSWER']}])
def test_failed_or_invalid_source_does_not_prevent_other_source(page):
    h = Harness([{'ids': ['S1', 'S2']}])
    h.pages[ITEMS[0]['url']] = page
    result = h.run()
    assert result['status'] == 'found'
    assert result['sources'] == [ITEMS[1]['url']]
    assert 'UNVERIFIED ANSWER' not in result['reply']
    assert h.reader.call_count == 2


@pytest.mark.parametrize('phase', ['provider', 'ranking', 'reader', 'comparison'])
def test_total_deadline_discards_late_answer(phase):
    h = Harness()
    def expire(value):
        h.now = 120
        return value
    if phase == 'provider':
        h.provider.side_effect = lambda *a, **k: expire(h.items)
    elif phase == 'ranking':
        h.responses = iter([lambda *a: expire({'ids': ['S1']})])
    elif phase == 'reader':
        h.pages[ITEMS[0]['url']] = lambda: expire({'status': 'found'})
    else:
        h.responses = iter([{'ids': ['S1', 'S2']},
                            lambda *a: expire({'relation': 'consistent'})])
    result = h.run()
    assert result['status'] == 'limit'
    assert '17 euros' not in result['reply']


def test_cancellation_inside_reader_is_not_swallowed_as_site_failure():
    h = Harness()
    def stop(session, url, question, **kwargs):
        h.stopped = True
        kwargs['cancelled']()
    h.reader.side_effect = stop
    with pytest.raises(ValueError, match='search_cancelled'):
        h.run()
    assert h.reader.call_count == 1


@pytest.mark.parametrize('source', ['twitch', 'discord', 'remote', ''])
def test_external_source_rejected_before_provider(source):
    h = Harness()
    with pytest.raises(ValueError, match='local_search_required'):
        h.run(source=source)
    h.provider.assert_not_called()
def test_provider_unavailability_is_not_a_claim_that_information_is_missing():
    from unittest.mock import Mock
    from public_web_search import read_search
    provider = Mock(side_effect=RuntimeError('resource_http_status_429'))
    reader = Mock()
    result = read_search(Mock(), 'Horaires Louvre', provider=provider, reader=reader)
    assert result['status'] == 'failed'
    assert 'moteur de recherche est indisponible' in result['reply']
    reader.assert_not_called()
