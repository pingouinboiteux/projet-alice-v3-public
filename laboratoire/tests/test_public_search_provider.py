"""Public search fixtures: no network, model or personal memory."""
from unittest.mock import Mock
import pytest
import public_search_provider as search


def reply(html):
    return {'url': search.ENDPOINT, 'mime': 'text/html', 'status': 200,
            'body': html.encode('utf-8')}


def run(html, **kwargs):
    return search.search_public('documentation Python', Mock(), fetcher=Mock(return_value=reply(html)), **kwargs)


def link(url='https://docs.python.org/', title='Documentation', cls='result__a'):
    return f'<a class="{cls}" href="{url}">{title}</a>'


def test_public_get_bounded_query_guard_and_no_snippets():
    check = Mock()
    fetch = Mock(return_value=reply(link(title='Python <b>docs</b> &amp; aide') + '<p>UNTRUSTED SNIPPET</p>'))
    rows = search.search_public('café & Python', check, fetcher=fetch)
    assert rows == [{'id': 'S1', 'title': 'Python docs & aide', 'url': 'https://docs.python.org/'}]
    assert fetch.call_args.args[0] == search.ENDPOINT + '?q=caf%C3%A9+%26+Python'
    assert fetch.call_args.kwargs == {'kind': 'document', 'allowed_origin': search.PROVIDER_ORIGIN, 'deadline': None}
    assert check.call_count == 3


@pytest.mark.parametrize('prefix', ['//duckduckgo.com/l/?uddg=', '/l/?uddg=', 'https://html.duckduckgo.com/l/?uddg='])
def test_known_wrappers_only(prefix):
    rows = run(link(prefix + 'https%3A%2F%2Fdocs.python.org%2F3%2F'))
    assert rows[0]['url'] == 'https://docs.python.org/3/'


@pytest.mark.parametrize('url', [
    'http://docs.python.org/', 'https://127.0.0.1/', 'https://localhost/',
    'https://host.internal/', 'https://u:p@example.org/', 'https://example.org:8443/',
    'javascript:alert(1)', 'https://example.org/file.zip', 'https://example.org/file.pdf',
    'https://duckduckgo.com/', 'https://www.google.com/search?q=x',
    'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org&uddg=https%3A%2F%2Fexample.com',
    'https://bad..org/', 'https://bad_host.org/',
])
def test_unsafe_candidates_excluded(url):
    assert run(link(url) + link())[0]['url'] == 'https://docs.python.org/'


def test_cap_deduplication_canonical_and_other_anchors_ignored():
    html = link('https://DOCS.PYTHON.ORG.:443/#section') + link()
    html += link('https://bad.org/', cls='other')
    html += ''.join(link(f'https://example.org/{i}') for i in range(20))
    rows = run(html)
    assert len(rows) == 8 and rows[0]['url'] == 'https://docs.python.org/'
    assert [r['id'] for r in rows] == [f'S{i}' for i in range(1, 9)]
    assert all(r['url'] != 'https://bad.org/' for r in rows)


def test_malformed_empty_attributes_and_third_party_wrapper_not_decoded():
    rows = run('<div class><a class href>x</a></div>' + link('https://redirect.example.org/?uddg=https%3A%2F%2Fdocs.python.org'))
    assert rows[0]['url'].startswith('https://redirect.example.org/')


@pytest.mark.parametrize('wrapper', ['<div class="result result--ad">{}</div>', '<div hidden>{}</div>',
    '<div aria-hidden="true">{}</div>', '<template>{}</template>', '<script>{}</script>'])
def test_ads_and_hidden_anchors_ignored(wrapper):
    assert len(run(wrapper.format(link('https://ads.example.org/')) + link())) == 1


@pytest.mark.parametrize('query', ['', '  ', 'x' * 501, 'a\nb', None, 1, 'a\x7fb'])
def test_query_refused_before_fetch(query):
    fetch = Mock()
    with pytest.raises(ValueError):
        search.search_public(query, Mock(), fetcher=fetch)
    fetch.assert_not_called()


@pytest.mark.parametrize('html', ['<p>No results</p>', '<a href="https://docs.python.org">x</a>',
    '<form id="anomaly-form">' + link() + '</form>'])
def test_empty_layout_or_challenge_is_explicit_failure(html):
    with pytest.raises(RuntimeError):
        run(html)


@pytest.mark.parametrize('status', [202, 403, 429])
def test_no_retry_or_bypass(status):
    fetch = Mock(side_effect=RuntimeError('resource_http_status_' + str(status)))
    with pytest.raises(RuntimeError, match=str(status)):
        search.search_public('test', Mock(), fetcher=fetch)
    assert fetch.call_count == 1


def test_guard_and_deadline_stop_before_fetch():
    fetch = Mock()
    with pytest.raises(RuntimeError, match='RAM'):
        search.search_public('test', Mock(side_effect=RuntimeError('RAM')), fetcher=fetch)
    with pytest.raises(RuntimeError, match='deadline'):
        search.search_public('test', Mock(), fetcher=fetch, deadline=0)
    fetch.assert_not_called()


def test_transport_failure_explicit_without_retry():
    fetch = Mock(side_effect=OSError('offline'))
    with pytest.raises(RuntimeError, match='transport_unavailable'):
        search.search_public('test', Mock(), fetcher=fetch)
    assert fetch.call_count == 1


@pytest.mark.parametrize('change', [{'url': 'https://other.org/'}, {'mime': 'text/plain'}, {'status': 202},
    {'body': b'\xff'}, {'body': b'x' * (search.LIMIT + 1)}])
def test_invalid_response(change):
    response = reply(link()); response.update(change)
    with pytest.raises((ValueError, RuntimeError)):
        search.search_public('test', Mock(), fetcher=Mock(return_value=response))
