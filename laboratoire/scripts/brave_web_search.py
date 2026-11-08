"""Search by typing in a visible, dedicated local Brave window.

Page text and links are observations, not instructions. Only observed links can
be opened. No RSS/API search or page retrieval outside the browser is used.
"""
import time
from urllib.parse import urljoin

from public_navigation import canonical_url
from public_resources import origin
from web_source_selection import rank_results, compare_evidence
from public_goal_navigation import choose
from web_evidence import assess, confirm_relevance
from web_passages import select_passages
from brave_desktop_browser import BraveDesktopBrowser


def link_options(snapshot, *, external=False, scope=None, seen=()):
    """IDs refer to observed anchors, not arbitrary selectors or model URLs."""
    links = snapshot['links']
    base = links['url']
    options, urls = [], set(seen)
    for index, link in enumerate(links['links']):
        if link.get('download'):
            continue
        try:
            href = link['href'].strip()
            if not href or href.startswith('#') or any(ord(c) < 32 for c in href):
                continue
            url = canonical_url(urljoin(base, href))
            site = origin(url)
        except (ValueError, UnicodeError):
            continue
        if url in urls or url == canonical_url(base):
            continue
        if external and site == origin(base):
            continue
        if scope is not None and site != scope:
            continue
        urls.add(url)
        options.append({'id': 'S'+str(len(options)+1), 'title': link['label'][:300],
                        'url': url, 'index': index})
        if len(options) == 8:
            break
    return options


def settle(browser, guard):
    before = browser.observe()
    count = 0
    for _ in range(10):
        guard()
        browser.page.wait_for_timeout(150)
        after = browser.observe()
        same = (before['page']['revision'] == after['page']['revision'] and
                before['links']['revision'] == after['links']['revision'])
        count = count + 1 if same else 0
        if count >= 3:
            return after
        before = after
    raise ValueError('brave_page_unstable')


def read_brave_search(session, question, *, source='text', factory=BraveDesktopBrowser,
                      cancelled=lambda: False, clock=time.monotonic):
    if source not in ('text', 'voice'):
        raise ValueError('local_brave_request_required')
    if type(question) is not str or not question.strip() or len(question) > 500:
        raise ValueError('invalid_brave_question')
    deadline = clock() + 90
    evidence, attempts = [], []
    previous = getattr(session, 'browser_demo', None)

    def guard():
        session.check()
        if cancelled():
            raise ValueError('brave_search_cancelled')
        if clock() >= deadline:
            raise TimeoutError('brave_search_deadline')

    def result(status, reply, **extra):
        return {'status': status, 'reply': reply, 'sources': [e['url'] for e in evidence],
                'attempts': list(attempts), 'partial': True, **extra}

    guard()
    browser = factory(guard)
    session.browser_demo = browser
    try:
        browser.start()
        browser.search(question)
        snapshot = settle(browser, guard)
        search_url = browser.target
        options = link_options(snapshot, external=True)
        if not options:
            return result('missing', 'Je ne vois pas de lien de resultat exploitable dans Brave. '
                          'La page peut demander une intervention ou ne pas fournir de resultat.')
        chosen = rank_results(session, question, [{k: v for k, v in item.items() if k != 'index'} for item in options])
        guard()
        for step, item in enumerate(chosen):
            try:
                guard()
                if step:
                    browser.start_url(search_url)
                # Ranking can outlast the observation; find the same selected
                # URL again in fresh results instead of reusing its old index.
                snapshot = settle(browser, guard)
                matches = [link for link in link_options(snapshot, external=True) if link['url'] == item['url']]
                if not matches:
                    attempts.append({'url': item['url'], 'status': 'result_changed'})
                    continue
                browser.open_observed(snapshot, matches[0]['index'])
                seen = set()
                scope = origin(item['url'])
                for depth in range(2):
                    guard()
                    current = settle(browser, guard)
                    url = canonical_url(browser.target)
                    if origin(url) != scope or url in seen:
                        raise ValueError('brave_source_scope_changed')
                    seen.add(url)
                    page_source = {**select_passages(current['page']['text'], question), 'truncated': True}
                    decision = assess(session, question, page_source)
                    guard()
                    if not browser.current(current):
                        raise ValueError('brave_page_changed')
                    if decision['status'] == 'found':
                        decision = confirm_relevance(session, question, decision)
                        guard()
                        if not browser.current(current):
                            raise ValueError('brave_page_changed')
                    if decision['status'] in ('found', 'ambiguous'):
                        evidence.append({'url': url, 'quotes': decision['quotes'], 'status': decision['status']})
                        attempts.append({'url': item['url'], 'status': decision['status'], 'visited': list(seen)})
                        break
                    if decision['status'] == 'invalid':
                        raise ValueError('brave_evidence_invalid')
                    following = link_options(current, scope=scope, seen=seen)
                    if depth == 1 or not following:
                        attempts.append({'url': item['url'], 'status': 'missing', 'visited': list(seen)})
                        break
                    choice = choose(session, question, [{'id': f['id'], 'label': f['title'], 'url': f['url']}
                                                       for f in following], list(seen))
                    guard()
                    if choice is None:
                        attempts.append({'url': item['url'], 'status': 'missing', 'visited': list(seen)})
                        break
                    target = next(f for f in following if f['id'] == choice['id'])
                    browser.open_observed(current, target['index'])
            except (ValueError, RuntimeError, OSError) as error:
                guard()
                attempts.append({'url': item['url'], 'status': 'failed', 'error_type': type(error).__name__})
        guard()
        if not evidence:
            return result('missing', 'J ai effectue la recherche dans Brave, mais je n ai pas pu verifier '
                          'de reponse dans les pages consultees.')
        relation = 'single'
        if len(evidence) > 1:
            try:
                relation = compare_evidence(session, question, evidence)
            except (ValueError, TypeError, KeyError):
                relation = 'inconclusive'
            guard()
        ambiguous = relation in ('conflicting', 'inconclusive') or any(e['status'] == 'ambiguous' for e in evidence)
        prefix = ('Les extraits ne permettent pas de trancher ; voici ce que les pages indiquent.\n' if ambiguous else
                  'Voici les extraits verifies dans Brave.\n')
        if len(evidence) == 1:
            prefix += 'Une seule source a pu etre verifiee.\n'
        reply = prefix + '\n'.join('Source '+str(i+1)+' :\n' + '\n'.join('« '+q+' »' for q in e['quotes'])
                                  for i, e in enumerate(evidence))
        return result('ambiguous' if ambiguous else 'found', reply, evidence=evidence, relation=relation)
    except TimeoutError:
        session.check()
        if cancelled():
            raise ValueError('brave_search_cancelled')
        return result('limit', 'Le delai de recherche est atteint. Je m arrete sans confirmer de reponse.')
    finally:
        try:
            browser.close()
        finally:
            session.browser_demo = previous
