"""Orchestration only: fake browser/model; no network, UI, audio or memories."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brave_web_search as module
import web_source_selection as selection

SEARCH = 'https://search.brave.com/search?q=validation'


def snapshot(url, links=(), text='Le tarif est 12 euros.', revision='stable'):
    return {'page': {'text': text, 'revision': revision},
            'links': {'url': url, 'revision': revision,
                      'links': [{'label': label, 'href': href} for label, href in links]}}


class Session:
    def __init__(self, answers=()):
        self.answers = iter(answers)
        self.browser_demo = object()
        self.check = Mock()
        self.calls = []

    def ask(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        answer = next(self.answers)
        if callable(answer):
            answer = answer(messages)
        return json.dumps(answer), None, None


class Browser:
    def __init__(self, session, pages):
        self.session = session
        self.pages = pages
        self.target = SEARCH
        self.page = SimpleNamespace(wait_for_timeout=lambda _: None)
        self.events = []
        self.fresh = True
        self.on_return = None
        self.on_search = None

    def factory(self, guard):
        self.guard = guard
        return self

    def start(self):
        self.events.append(('start',))

    def search(self, question):
        self.events.append(('search', question))
        if self.on_search:
            self.on_search()

    def start_url(self, url):
        self.events.append(('return', url))
        self.target = url
        if self.on_return:
            self.on_return()

    def observe(self):
        return self.pages[self.target]

    def current(self, observed):
        return self.fresh and observed is self.pages[self.target]

    def open_observed(self, observed, index):
        assert self.current(observed), 'stale fake browser observation'
        assert type(index) is int
        self.events.append(('open', observed, index))
        self.target = module.canonical_url(module.urljoin(
            self.target, observed['links']['links'][index]['href']))

    def close(self):
        assert self.session.browser_demo is self
        self.events.append(('close',))


def setup_case(answers=(), count=1):
    session = Session(answers)
    pages = {SEARCH: snapshot(SEARCH, [('Source '+str(i), f'https://site{i}.org/')
                                     for i in range(count)])}
    pages.update({f'https://site{i}.org/': snapshot(f'https://site{i}.org/') for i in range(count)})
    return session, Browser(session, pages)


def found(messages):
    passage = json.loads(messages[-1]['content'])['passages'][0]
    return {'status': 'found', 'evidence': [{'passage': passage['id'], 'quote': passage['text']}]}


def run(session, browser, **kwargs):
    return module.read_brave_search(session, 'Quel est le tarif ?', factory=browser.factory, **kwargs)


def test_typed_search_observed_index_and_exact_evidence():
    session, browser = setup_case([{'ids': ['S1']}, found, found])
    previous = session.browser_demo
    result = run(session, browser)
    assert result['status'] == 'found'
    assert result['sources'] == ['https://site0.org/']
    assert 'Le tarif est 12 euros.' in result['reply']
    assert result['partial'] is True
    assert browser.events[1] == ('search', 'Quel est le tarif ?')
    assert browser.events[2] == ('open', browser.pages[SEARCH], 0)
    assert browser.events[-1] == ('close',)
    assert session.browser_demo is previous


def test_irrelevant_exact_quote_is_not_promoted_to_answer():
    session, browser = setup_case([{'ids': ['S1']}, found,
                                  {'status': 'missing', 'evidence': []}])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert result['sources'] == []
    assert browser.events[-1] == ('close',)


def test_page_change_during_relevance_recheck_discards_answer():
    session, browser = setup_case()
    def changed(messages):
        browser.fresh = False
        return found(messages)
    session.answers = iter([{'ids': ['S1']}, found, changed])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert result['sources'] == []
    assert result['attempts'][0]['status'] == 'failed'


def test_results_reobserved_after_ranking_and_chosen_url_reidentified():
    session, browser = setup_case(count=2)
    def ranking(messages):
        browser.pages[SEARCH] = snapshot(SEARCH, [
            ('Source 1', 'https://site1.org/'), ('Source 0', 'https://site0.org/')], revision='new')
        return {'ids': ['S1']}
    session.answers = iter([ranking, found, found])
    result = run(session, browser)
    assert result['sources'] == ['https://site0.org/']
    opened = [event for event in browser.events if event[0] == 'open']
    assert opened[0][1] is browser.pages[SEARCH] and opened[0][2] == 1


def test_chosen_url_disappearing_during_ranking_is_not_opened():
    session, browser = setup_case()
    def ranking(messages):
        browser.pages[SEARCH] = snapshot(SEARCH, [('Replacement', 'https://other.org/')], revision='new')
        return {'ids': ['S1']}
    session.answers = iter([ranking])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert result['attempts'] == [{'url': 'https://site0.org/', 'status': 'result_changed'}]
    assert not any(event[0] == 'open' for event in browser.events)


@pytest.mark.parametrize('source', ['twitch', 'discord', 'web', None])
def test_external_requests_never_create_browser(source):
    factory = Mock()
    with pytest.raises(ValueError, match='local_brave'):
        module.read_brave_search(Session(), 'tarif', source=source, factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize('question', ['', ' ', 'a'*501, None, 12])
def test_invalid_question_never_creates_browser(question):
    factory = Mock()
    with pytest.raises(ValueError, match='invalid_brave_question'):
        module.read_brave_search(Session(), question, factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize('ids', [['https://invented.org/'], ['S9'], ['S1', 'S1'], ['S1']*4])
def test_model_cannot_invent_result_or_exceed_budget(ids):
    session, browser = setup_case([{'ids': ids}])
    previous = session.browser_demo
    with pytest.raises(ValueError):
        run(session, browser)
    assert not any(e[0] == 'open' for e in browser.events)
    assert browser.events[-1] == ('close',)
    assert session.browser_demo is previous


def test_candidate_filter_preserves_anchor_indices_and_bounds_inventory():
    links = [('same', SEARCH), ('relative', '/other'), ('anchor', '#a'),
             ('local', 'https://127.0.0.1/'), ('file', 'file:///a'),
             ('valid', 'https://one.org/'), ('duplicate', 'https://one.org/'),
             ('download', 'https://download.org/')]
    links += [('extra', f'https://extra{i}.org/') for i in range(20)]
    snap = snapshot(SEARCH, links)
    snap['links']['links'][7]['download'] = True
    options = module.link_options(snap, external=True)
    assert len(options) == 8
    assert options[0] == {'id': 'S1', 'title': 'valid', 'url': 'https://one.org/', 'index': 5}
    assert options[-1]['id'] == 'S8'


def test_ranking_diversifies_origins_and_never_fetches():
    session = Session([{'ids': ['S1', 'S2', 'S3']}])
    items = [{'id': 'S1', 'url': 'https://one.org/a'},
             {'id': 'S2', 'url': 'https://one.org/b'},
             {'id': 'S3', 'url': 'https://two.org/'}]
    assert selection.rank_results(session, 'tarif', items) == [items[0], items[2]]


def test_three_sources_two_pages_each_maximum():
    answers = [{'ids': ['S1', 'S2', 'S3']}]
    for _ in range(3):
        answers += [{'status': 'missing', 'evidence': []}, {'link': 'S1'},
                    {'status': 'missing', 'evidence': []}]
    session, browser = setup_case(answers, count=4)
    for i in range(4):
        base = f'https://site{i}.org/'
        browser.pages[base] = snapshot(base, [('Details', base+'details'), ('Other', 'https://escape.org/')])
        browser.pages[base+'details'] = snapshot(base+'details', [('More', base+'third')])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert len(result['attempts']) == 3
    assert all(len(a['visited']) == 2 for a in result['attempts'])
    assert len([e for e in browser.events if e[0] == 'open']) == 6
    assert len([e for e in browser.events if e[0] == 'return']) == 2


def test_changed_search_results_are_not_opened_from_old_snapshot():
    session, browser = setup_case([{'ids': ['S1', 'S2']}, found, found], count=2)
    browser.on_return = lambda: browser.pages.update({SEARCH: snapshot(SEARCH)})
    result = run(session, browser)
    assert result['sources'] == ['https://site0.org/']
    assert result['attempts'][-1]['status'] == 'result_changed'
    assert len([e for e in browser.events if e[0] == 'open']) == 1


def test_page_changed_during_model_read_rejects_evidence():
    session, browser = setup_case([{'ids': ['S1']}])
    def changed(messages):
        browser.fresh = False
        return found(messages)
    session.answers = iter([{'ids': ['S1']}, changed])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert result['sources'] == []
    assert result['attempts'][0]['status'] == 'failed'


@pytest.mark.parametrize('relation', ['conflicting', 'inconclusive', 'consistent'])
def test_cross_source_comparison_keeps_quotes_and_uncertainty(relation):
    session, browser = setup_case([{'ids': ['S1', 'S2']}, found, found, found, found,
                                  {'relation': relation, 'same_conditions': True}], count=2)
    browser.pages['https://site1.org/']['page']['text'] = 'Le tarif est 15 euros.'
    result = run(session, browser)
    assert result['status'] == ('found' if relation == 'consistent' else 'ambiguous')
    assert result['relation'] == relation
    assert '12 euros' in result['reply'] and '15 euros' in result['reply']


def test_fabricated_quote_is_rejected():
    session, browser = setup_case([{'ids': ['S1']},
                                  {'status': 'found', 'evidence': [{'passage': 'p1', 'quote': 'Invented'}]}])
    result = run(session, browser)
    assert result['status'] == 'missing' and result['sources'] == []


def test_invented_followup_link_is_not_navigated():
    session, browser = setup_case([{'ids': ['S1']}, {'status': 'missing', 'evidence': []},
                                  {'link': 'https://invented.org/'}])
    browser.pages['https://site0.org/'] = snapshot('https://site0.org/', [('Detail', '/detail')])
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert result['attempts'][0]['status'] == 'failed'
    assert len([e for e in browser.events if e[0] == 'open']) == 1


def test_redirect_to_another_source_is_not_assessed():
    session, browser = setup_case([{'ids': ['S1']}])
    browser.pages['https://escape.org/'] = snapshot('https://escape.org/')
    original_open = browser.open_observed
    def redirect(observed, index):
        original_open(observed, index)
        browser.target = 'https://escape.org/'
    browser.open_observed = redirect
    result = run(session, browser)
    assert result['status'] == 'missing' and result['sources'] == []
    assert len(session.calls) == 1


def test_close_failure_still_restores_previous_browser():
    session, browser = setup_case(count=0)
    previous = session.browser_demo
    original_close = browser.close
    def broken_close():
        original_close()
        raise RuntimeError('close failed')
    browser.close = broken_close
    with pytest.raises(RuntimeError, match='close failed'):
        run(session, browser)
    assert session.browser_demo is previous


def test_resource_guard_failure_closes_browser():
    session, browser = setup_case()
    previous = session.browser_demo
    def fail_guard():
        session.check.side_effect = RuntimeError('resource limit')
    browser.on_search = fail_guard
    with pytest.raises(RuntimeError, match='resource limit'):
        run(session, browser)
    assert browser.events[-1] == ('close',)
    assert session.browser_demo is previous


def test_no_results_has_no_model_call():
    session, browser = setup_case(count=0)
    result = run(session, browser)
    assert result['status'] == 'missing'
    assert session.calls == []


def test_cancellation_closes_before_restoring_guard_browser():
    session, browser = setup_case()
    previous = session.browser_demo
    cancelled = [False]
    browser.on_search = lambda: cancelled.__setitem__(0, True)
    with pytest.raises(ValueError, match='brave_search_cancelled'):
        run(session, browser, cancelled=lambda: cancelled[0])
    assert browser.events[-1] == ('close',)
    assert session.browser_demo is previous


def test_ninety_second_deadline_closes_browser():
    session, browser = setup_case()
    now = [0]
    browser.on_search = lambda: now.__setitem__(0, 90)
    previous = session.browser_demo
    result = run(session, browser, clock=lambda: now[0])
    assert result['status'] == 'limit'
    assert result['sources'] == []
    assert browser.events[-1] == ('close',)
    assert session.browser_demo is previous


def test_unstable_page_never_reaches_model():
    session, browser = setup_case()
    revisions = iter(range(50))
    browser.observe = lambda: snapshot(SEARCH, revision=str(next(revisions)))
    with pytest.raises(ValueError, match='brave_page_unstable'):
        run(session, browser)
    assert session.calls == []
    assert browser.events[-1] == ('close',)


def test_source_selection_and_orchestrator_have_no_search_transport_imports():
    for source in (module, selection):
        tree = ast.parse(Path(source.__file__).read_text(encoding='utf-8'))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
        assert not any(name and (name.startswith(('requests', 'httpx', 'urllib.request', 'feedparser'))
                                  or name == 'web_search') for name in imports)


@pytest.mark.parametrize('stage', ['search', 'observe', 'close'])
@pytest.mark.parametrize('kind', ['timeout', 'closed'])
def test_browser_failure_returns_to_dialogue_and_allows_next_request(stage, kind):
    from playwright.sync_api import Error, TimeoutError as BrowserTimeout
    from search_dialogue import SearchDialogue
    session, browser = setup_case(count=0)
    previous = session.browser_demo
    original = getattr(browser, stage)
    failure = BrowserTimeout('validation timeout') if kind == 'timeout' else Error('validation closed')
    def fail(*args, **kwargs):
        if stage == 'close': original(*args, **kwargs)
        raise failure
    setattr(browser, stage, fail)
    planner = Mock(return_value={'status':'ready','target':{'question':'validation tarif'}})
    def reader(session, question, **kwargs):
        return module.read_brave_search(session, question, factory=browser.factory, **kwargs)
    dialogue = SearchDialogue(session, planner=planner, reader=reader)
    result = dialogue.handle('/rechercher validation tarif', 'text')
    assert result['status'] == 'failed'
    assert 'Aucune information Web confirmee' in result['reply']
    assert not dialogue.turns
    assert session.browser_demo is previous
    assert browser.events[-1] == ('close',)
    setattr(browser, stage, original)
    assert dialogue.handle('/rechercher validation tarif', 'text')['status'] == 'missing'


def test_unexpected_programming_error_is_not_hidden_as_browser_failure():
    from search_dialogue import SearchDialogue
    dialogue = SearchDialogue(Session(), planner=Mock(side_effect=TypeError('validation bug')))
    with pytest.raises(TypeError, match='validation bug'):
        dialogue.handle('/rechercher validation tarif', 'text')
