"""Bing RSS shape and trust boundary, without real network."""
from unittest.mock import Mock
import pytest
import public_search_bing as bing
from public_resources import MIMES


def item(url='https://docs.python.org/', title='Python docs'):
    return f'<item><title>{title}</title><link>{url}</link><description>NOT EVIDENCE</description></item>'


def feed(items):
    return ('<rss version="2.0"><channel>' + items + '</channel></rss>').encode()


def test_valid_bounded_feed_deduplicates_without_descriptions():
    rows = bing.parse_feed(feed(item() * 2 + ''.join(item(f'https://example.org/{n}') for n in range(12))))
    assert len(rows) == 8
    assert rows[0] == {'id': 'S1', 'title': 'Python docs', 'url': 'https://docs.python.org/'}
    assert rows[-1]['id'] == 'S8'


@pytest.mark.parametrize('body', [b'<!DOCTYPE rss><rss/>', b'<!ENTITY x "y"><rss/>',
    '<!DOCTYPE rss><rss/>'.encode('utf-16'), b'<rss>\x00</rss>', b'<rss>', b'<html/>',
    feed(''), feed(item('http://example.org/')), feed(item('https://127.0.0.1/')),
    feed('<item><title>one</title><title>two</title><link>https://example.org/</link></item>'),
    b'x' * (bing.LIMIT + 1)])
def test_xml_and_unsafe_results_fail_explicitly(body):
    with pytest.raises((ValueError, RuntimeError)):
        bing.parse_feed(body)


def test_feed_transport_pinned_origin_and_no_document_accept_change():
    fetch = Mock(return_value={'url': bing.ENDPOINT, 'status': 200,
                              'mime': 'text/xml', 'body': feed(item())})
    check = Mock()
    assert bing.search_public('Python & docs', check, fetcher=fetch)[0]['id'] == 'S1'
    assert fetch.call_args.args[0] == 'https://www.bing.com/search?q=Python+%26+docs&format=rss'
    assert fetch.call_args.kwargs == {'kind': 'feed', 'allowed_origin': bing.PROVIDER_ORIGIN, 'deadline': None}
    assert check.call_count == 3
    assert MIMES['document'] == {'text/html', 'application/xhtml+xml', 'text/plain'}


@pytest.mark.parametrize('change', [{'mime': 'text/html'}, {'status': 429}, {'url': 'https://other.org/'}])
def test_response_refused(change):
    response = {'url': bing.ENDPOINT, 'status': 200, 'mime': 'text/xml', 'body': feed(item())}
    response.update(change)
    with pytest.raises(RuntimeError):
        bing.search_public('Python', Mock(), fetcher=Mock(return_value=response))


@pytest.mark.parametrize('query', ['', None, 'x' * 501, 'a\nb'])
def test_invalid_query_no_network(query):
    fetch = Mock()
    with pytest.raises(ValueError):
        bing.search_public(query, Mock(), fetcher=fetch)
    fetch.assert_not_called()


def test_guard_deadline_and_transport_failure_no_retry():
    fetch = Mock(side_effect=OSError('offline'))
    with pytest.raises(RuntimeError, match='deadline'):
        bing.search_public('Python', Mock(), fetcher=fetch, deadline=0)
    fetch.assert_not_called()
    with pytest.raises(RuntimeError, match='transport_unavailable'):
        bing.search_public('Python', Mock(), fetcher=fetch)
    assert fetch.call_count == 1
