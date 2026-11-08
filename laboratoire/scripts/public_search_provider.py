"""Bounded public search discovery; titles/URLs are untrusted, never evidence.

Uses DuckDuckGo's documented non-JavaScript HTML endpoint without accounts,
cookies or bypasses. A block or an unknown HTML layout fails closed.
"""
from html.parser import HTMLParser
import math
import re
import time
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit, urlunsplit

from action_policy import validate_url
from public_resources import LIMIT, fetch_resource, origin

ENDPOINT = 'https://html.duckduckgo.com/html/'
PROVIDER_ORIGIN = origin(ENDPOINT)
_PROVIDERS = ('duckduckgo.com', 'google.com', 'bing.com', 'yahoo.com')
_DOWNLOAD = re.compile(r'\.(?:pdf|docx?|xlsx?|pptx?|apk|dmg|pkg|deb|rpm|gz|tar|mp[34]|wav|ogg|png|jpe?g|gif|webp)$', re.I)
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


def _destination(href):
    if href.startswith('//'):
        href = 'https:' + href
    elif href.startswith('/l/?'):
        href = 'https://duckduckgo.com' + href
    parsed = urlsplit(href)
    if parsed.hostname in {'duckduckgo.com', 'www.duckduckgo.com', 'html.duckduckgo.com'} and parsed.path == '/l/':
        validate_url(href)
        values = parse_qs(parsed.query).get('uddg', [])
        if len(values) != 1:
            raise ValueError('search_redirect_invalid')
        href = values[0]
    validate_url(href)
    parsed = urlsplit(href)
    host = origin(href)[1]
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) or any(
            not part or part.startswith('-') or part.endswith('-') for part in host.split('.')):
        raise ValueError('search_host_invalid')
    if any(host == domain or host.endswith('.' + domain) for domain in _PROVIDERS):
        raise ValueError('search_provider_link')
    if _DOWNLOAD.search(unquote(parsed.path).rstrip('/')):
        raise ValueError('search_download')
    return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))


class _Results(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.current = None
        self.rows = []
        self.blocked = False

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or '' for key, value in attrs}
        classes = set(attrs.get('class', '').lower().split())
        forbidden = tag in {'script', 'style', 'noscript', 'template'} or bool(classes & {
            'result--ad', 'result--ads', 'result__ad', 'ads', 'ad', 'sponsored'})
        forbidden |= 'hidden' in attrs or attrs.get('aria-hidden', '').lower() == 'true'
        if (any(marker in attrs.get('id', '').lower() for marker in ('anomaly', 'captcha', 'challenge')) or
                'anomaly.js' in attrs.get('action', '').lower()):
            self.blocked = True
        inherited = bool(self.stack and self.stack[-1][1])
        if tag not in _VOID:
            self.stack.append((tag, forbidden or inherited))
        if tag == 'a':
            self.current = None
            if 'result__a' in classes and not forbidden and not inherited:
                try:
                    self.current = (_destination(attrs.get('href', '')), [])
                except (ValueError, UnicodeError):
                    pass

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            url, parts = self.current
            title = ' '.join(''.join(parts).split())[:240]
            if title and url not in {row['url'] for row in self.rows} and len(self.rows) < 8:
                self.rows.append({'id': 'S' + str(len(self.rows) + 1), 'title': title, 'url': url})
            self.current = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.current and not (self.stack and self.stack[-1][1]):
            self.current[1].append(data)


def search_public(query, check, *, fetcher=fetch_resource, deadline=None):
    """Return at most eight untrusted {id,title,url} candidates, or fail explicitly.

    DNS/public-address validation happens again when a candidate is actually read.
    Search summaries are deliberately discarded: they cannot support an answer.
    """
    if (type(query) is not str or not query.strip() or len(query) > 500 or
            any(ord(c) < 32 or ord(c) == 127 for c in query) or not callable(check)):
        raise ValueError('search_query_invalid')
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise ValueError('search_deadline_invalid')
    def guard():
        check()
        if deadline is not None and time.monotonic() >= deadline:
            raise RuntimeError('search_deadline_exceeded')
    guard()
    try:
        resource = fetcher(ENDPOINT + '?q=' + quote_plus(query.strip()), guard,
                           kind='document', allowed_origin=PROVIDER_ORIGIN, deadline=deadline)
    except OSError as exc:
        raise RuntimeError('search_transport_unavailable') from exc
    guard()
    if (resource.get('status') != 200 or origin(resource.get('url', '')) != PROVIDER_ORIGIN or
            resource.get('mime') not in {'text/html', 'application/xhtml+xml'}):
        raise RuntimeError('search_response_refused')
    body = resource.get('body')
    if type(body) is not bytes or len(body) > LIMIT:
        raise ValueError('search_body_invalid')
    try:
        html = body.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise ValueError('search_encoding_invalid') from exc
    parser = _Results()
    parser.feed(html)
    parser.close()
    guard()
    if parser.blocked:
        raise RuntimeError('search_provider_blocked')
    if not parser.rows:
        raise RuntimeError('search_no_usable_results')
    return parser.rows
