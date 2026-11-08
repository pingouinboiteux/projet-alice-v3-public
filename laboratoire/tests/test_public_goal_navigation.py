"""Goal navigation with synthetic pages/models only; no network or private state."""
import copy
import json
from unittest.mock import Mock

import pytest

from public_goal_navigation import read_goal

URL = 'https://example.org/start'
MISSING = {'status': 'missing', 'evidence': []}


class Harness:
    def __init__(self, pages, responses):
        self.pages = pages
        self.responses = iter(responses)
        self.previous = object()
        self.session = Mock(browser_demo=self.previous)
        self.session.ask.side_effect = self.ask
        self.backends = []
        self.started = []
        self.now = 0
        self.stopped = False

    def ask(self, messages, **kwargs):
        response = next(self.responses)
        if callable(response):
            response = response(messages, kwargs)
        return (response if isinstance(response, str) else json.dumps(response)), 0, {}

    def factory(self, guard):
        if self.backends:
            self.backends[-1].close.assert_called_once()
        b = Mock()
        b.current.return_value = True
        self.backends.append(b)

        def start(url):
            self.started.append(url)
            spec = self.pages[url]
            b.target = spec.get('redirect', url)
            b.page.url = b.target
            b.data = {'url': b.target, 'links': spec.get('links', []),
                      'truncated': spec.get('truncated', False)}
            b.observe.return_value = {'revision': 'stable',
                                      'text': spec.get('text', 'Accueil public.'),
                                      'truncated': False, 'limitations': []}
            b.page.evaluate.side_effect = lambda *args: copy.deepcopy(b.data)
            if 'setup' in spec:
                spec['setup'](b)
            guard()

        b.start_url.side_effect = start
        return b

    def run(self, **kwargs):
        try:
            return read_goal(self.session, URL, 'Quel tarif ?', factory=self.factory,
                             cancelled=lambda: self.stopped, clock=lambda: self.now, **kwargs)
        finally:
            assert self.session.browser_demo is self.previous
            for backend in self.backends:
                backend.close.assert_called_once()
                backend.page.click.assert_not_called()


def found(messages, kwargs):
    passage = json.loads(messages[1]['content'])['passages'][0]
    return {'status': 'found', 'evidence': [{'passage': passage['id'], 'quote': 'Tarif : 17 euros.'}]}


def test_three_pages_follow_only_observed_ids_and_quote_final_page():
    h = Harness({URL: {'links': [{'label': 'Visites', 'href': '/visites'}]},
                 'https://example.org/visites': {'links': [{'label': 'Tarifs', 'href': '/tarifs'}]},
                 'https://example.org/tarifs': {'text': 'Tarif : 17 euros.'}},
                [MISSING, {'link': 'l1'}, MISSING, {'link': 'l1'}, found])
    result = h.run(source='voice')
    assert result['status'] == 'found'
    assert result['visited'] == h.started
    assert result['url'] == 'https://example.org/tarifs'
    assert '« Tarif : 17 euros. »' in result['reply']
    assert result['partial'] is True


def test_four_page_budget_never_opens_fifth_page():
    pages = {}
    urls = [URL] + ['https://example.org/page' + str(i) for i in range(1, 5)]
    for index, url in enumerate(urls[:-1]):
        pages[url] = {'links': [{'label': 'Suite', 'href': urls[index + 1]}]}
    h = Harness(pages, [MISSING, {'link': 'l1'}] * 3 + [MISSING])
    assert h.run()['status'] == 'limit'
    assert h.started == urls[:4]
    assert h.session.ask.call_count == 7


def test_search_two_page_budget_never_opens_third_page():
    h = Harness({URL: {'links': [{'label': 'Suite', 'href': '/next'}]},
                 'https://example.org/next': {'links': [{'label': 'Suite', 'href': '/third'}]}},
                [MISSING, {'link': 'l1'}, MISSING])
    result = h.run(max_pages=2)
    assert result['status'] == 'limit'
    assert h.started == [URL, 'https://example.org/next']
    assert h.session.ask.call_count == 3


@pytest.mark.parametrize('limit', [0, 5, True, 2.0, '2', None])
def test_invalid_page_budget_never_starts_backend(limit):
    h = Harness({}, [])
    with pytest.raises(ValueError):
        h.run(max_pages=limit)
    assert not h.backends


def test_structured_quotes_returned_with_exact_final_url_for_search():
    h = Harness({URL: {'text': 'Tarif : 17 euros.'}}, [found])
    result = h.run(max_pages=2)
    assert result['evidence'] == ['Tarif : 17 euros.']
    assert result['url'] == URL


@pytest.mark.parametrize('phase', ['assessment', 'selection', 'startup'])
def test_120_second_budget_discards_late_result_and_closes(phase):
    h = Harness({URL: {'text': 'Tarif : 17 euros.',
                      'links': [{'label': 'Suite', 'href': '/next'}]}}, [])

    def expired(messages, kwargs):
        h.now = 120
        return found(messages, kwargs) if phase == 'assessment' else {'link': 'l1'}

    h.responses = iter([expired] if phase == 'assessment' else [MISSING, expired])
    if phase == 'startup':
        h.pages[URL]['setup'] = lambda b: setattr(h, 'now', 120)
    result = h.run()
    assert result['status'] == 'limit'
    assert '17 euros' not in result['reply']
    assert h.started == [URL]


@pytest.mark.parametrize('links,truncated', [
    ([{'label': 'Fichier', 'href': '/next', 'download': True}], False),
    ([{'label': 'Tarifs', 'href': '/a'}, {'label': ' TARIFS ', 'href': '/b'}], False),
    ([{'label': 'Suite', 'href': 'https://other.org/page'}], False),
    ([{'label': 'Suite', 'href': 'https://sub.example.org/page'}], False),
    ([{'label': 'Suite', 'href': 'https://example.org:444/page'}], False),
    ([{'label': 'Suite', 'href': 'http://example.org/page'}], False),
    ([{'label': 'Suite', 'href': 'javascript:alert(1)'}], False),
    ([{'label': 'Suite', 'href': '#details'}], False),
    ([{'label': 'Suite', 'href': '/start'}], False),
    ([{'label': 'Suite', 'href': '/next'}], True),
])
def test_ineligible_links_never_reach_selector_or_open(links, truncated):
    h = Harness({URL: {'links': links, 'truncated': truncated}}, [MISSING])
    assert h.run()['status'] == 'missing'
    assert h.started == [URL]
    assert h.session.ask.call_count == 1


def test_duplicate_targets_are_offered_once():
    def selection(messages, kwargs):
        options = json.loads(messages[1]['content'])['liens_observes']
        assert options == [{'id': 'l1', 'label': 'Tarifs', 'url': 'https://example.org/next'}]
        return {'link': 'stop'}
    h = Harness({URL: {'links': [{'label': 'Tarifs', 'href': '/next'},
                                 {'label': 'Prix', 'href': '/next#details'}]}}, [MISSING, selection])
    assert h.run()['status'] == 'missing'


@pytest.mark.parametrize('length', [201, 1000])
def test_long_card_label_does_not_block_short_link_or_reach_model(length):
    long_label = 'x' * length
    def selection(messages, kwargs):
        options = json.loads(messages[1]['content'])['liens_observes']
        assert options == [{'id': 'l1', 'label': 'Tarifs', 'url': 'https://example.org/next'}]
        assert all(len(item['label']) <= 200 for item in options)
        assert long_label not in messages[1]['content']
        return {'link': 'l1'}
    h = Harness({URL: {'links': [{'label': long_label, 'href': '/long-card'},
                                 {'label': 'Tarifs', 'href': '/next'}]},
                 'https://example.org/next': {'text': 'Tarif : 17 euros.'}},
                [MISSING, selection, found])
    assert h.run()['status'] == 'found'
    assert h.started == [URL, 'https://example.org/next']


@pytest.mark.parametrize('raw', ['{"link":"l9"}', '{"link":"https://example.org/next"}',
                               '{"link":"l1","extra":true}', '{"link":null}',
                               '[]', 'not json', '{"link":"l1","link":"stop"}'])
def test_invalid_selector_never_navigates(raw):
    h = Harness({URL: {'links': [{'label': 'Suite', 'href': '/next'}]}}, [MISSING, raw])
    with pytest.raises(ValueError):
        h.run()
    assert h.started == [URL]


@pytest.mark.parametrize('redirect', [URL, 'https://other.org/page'])
def test_redirect_loop_or_cross_origin_stops_before_assessment(redirect):
    h = Harness({URL: {'links': [{'label': 'Suite', 'href': '/next'}]},
                 'https://example.org/next': {'redirect': redirect}}, [MISSING, {'link': 'l1'}])
    if redirect == URL:
        assert h.run()['status'] == 'missing'
    else:
        with pytest.raises(ValueError, match='scope_changed'):
            h.run()
    assert h.session.ask.call_count == 2


def test_same_origin_redirect_is_recorded_and_answered():
    h = Harness({URL: {'redirect': 'https://example.org/final', 'text': 'Tarif : 17 euros.'}}, [found])
    result = h.run()
    assert result['status'] == 'found'
    assert result['visited'] == ['https://example.org/final']


@pytest.mark.parametrize('phase', ['assessment', 'selection', 'links'])
def test_changed_page_or_links_discards_decision(phase):
    h = Harness({URL: {'text': 'Tarif : 17 euros.',
                      'links': [{'label': 'Suite', 'href': '/next'}]}}, [])
    def change(messages, kwargs):
        if phase == 'links':
            h.backends[-1].data['links'][0]['href'] = '/different'
        else:
            h.backends[-1].current.return_value = False
        return found(messages, kwargs) if phase == 'assessment' else {'link': 'l1'}
    h.responses = iter([change] if phase == 'assessment' else [MISSING, change])
    result = h.run()
    assert result['status'] == 'changed'
    assert '17 euros' not in result['reply']
    assert h.started == [URL]


@pytest.mark.parametrize('kind', ['text', 'links'])
def test_unstable_page_never_calls_model(kind):
    def setup(b):
        counter = iter(range(100))
        if kind == 'text':
            b.observe.side_effect = lambda: {'revision': str(next(counter)), 'text': 'Texte public.'}
        else:
            b.page.evaluate.side_effect = lambda *args: {
                'url': URL, 'links': [{'label': 'Suite', 'href': '/page' + str(next(counter))}],
                'truncated': False}
    h = Harness({URL: {'setup': setup}}, [])
    assert h.run()['status'] == 'unstable'
    h.session.ask.assert_not_called()


@pytest.mark.parametrize('raw', ['{"status":"found","evidence":[{"passage":"p1","quote":"Invented"}]}',
                               '{"status":"found","evidence":[]}', 'not json',
                               '{"status":"missing","status":"found","evidence":[]}'])
def test_unverified_evidence_never_delivers_answer(raw):
    h = Harness({URL: {'text': 'Tarif : 17 euros.'}}, [raw])
    assert h.run()['status'] == 'failed'


def test_ambiguous_evidence_keeps_both_exact_quotes_without_further_navigation():
    def ambiguous(messages, kwargs):
        p = json.loads(messages[1]['content'])['passages'][0]['id']
        return {'status': 'ambiguous', 'evidence': [{'passage': p, 'quote': q}
                    for q in ['Tarif : 17 euros.', 'Tarif : 23 euros.']]}
    h = Harness({URL: {'text': 'Tarif : 17 euros. Tarif : 23 euros.'}}, [ambiguous])
    result = h.run()
    assert result['status'] == 'ambiguous'
    assert '17 euros.' in result['reply'] and '23 euros.' in result['reply']
    assert h.started == [URL]


@pytest.mark.parametrize('phase', ['before', 'assessment', 'selection', 'between_pages'])
def test_cancel_always_closes_and_never_opens_next_page(phase):
    h = Harness({URL: {'links': [{'label': 'Suite', 'href': '/next'}]}}, [])
    def cancel(messages, kwargs):
        h.stopped = True
        return MISSING if phase == 'assessment' else {'link': 'l1'}
    h.responses = iter([cancel] if phase == 'assessment' else [MISSING, cancel])
    if phase == 'before':
        h.stopped = True
    elif phase == 'between_pages':
        h.responses = iter([MISSING, {'link': 'l1'}])
        h.pages[URL]['setup'] = lambda b: setattr(b.close, 'side_effect', lambda: setattr(h, 'stopped', True))
    with pytest.raises(ValueError, match='cancelled'):
        h.run()
    assert len(h.started) == (0 if phase == 'before' else 1)


@pytest.mark.parametrize('phase', ['start', 'check', 'model', 'close'])
def test_failure_restores_previous_session_backend(phase):
    h = Harness({URL: {}}, [MISSING])
    def setup(b):
        if phase == 'start':
            raise OSError('fixture failed')
        if phase == 'close':
            b.close.side_effect = RuntimeError('fixture failed')
        if phase == 'check':
            h.session.check.side_effect = RuntimeError('fixture failed')
    h.pages[URL]['setup'] = setup
    if phase == 'model':
        h.session.ask.side_effect = RuntimeError('fixture failed')
    with pytest.raises((OSError, RuntimeError), match='fixture failed'):
        h.run()


@pytest.mark.parametrize('source', ['twitch', 'discord', 'system', None])
def test_nonlocal_source_rejected_without_browser(source):
    h = Harness({}, [])
    with pytest.raises(ValueError, match='local_goal_required'):
        h.run(source=source)
    assert not h.backends


@pytest.mark.parametrize('question', ['', ' ', None, 'x' * 2001])
def test_invalid_question_rejected_without_browser(question):
    factory = Mock()
    with pytest.raises(ValueError, match='explicit_goal_required'):
        read_goal(Mock(), URL, question, factory=factory)
    factory.assert_not_called()
