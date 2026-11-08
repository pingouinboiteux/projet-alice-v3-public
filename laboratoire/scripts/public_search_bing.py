"""Explicit Bing public RSS search provider, without accounts or API secrets.

No fallback to/from another engine. RSS descriptions are not evidence.
"""
import math
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from public_resources import LIMIT, MIMES, fetch_resource, origin
from public_search_provider import _destination

ENDPOINT = 'https://www.bing.com/search'
PROVIDER_ORIGIN = origin(ENDPOINT)


def parse_feed(body):
    if type(body) is not bytes or len(body) > LIMIT:
        raise ValueError('search_body_invalid')
    try:
        # Decode before scanning: UTF-16/NUL tricks cannot hide declarations.
        text = body.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise ValueError('search_encoding_invalid') from exc
    if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('search_xml_declaration_refused')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError('search_xml_invalid') from exc
    if root.tag != 'rss' or len(root.findall('channel')) != 1:
        raise RuntimeError('search_feed_layout_unknown')
    rows = []
    for item in root.find('channel').findall('item'):
        if len(rows) >= 8:
            break
        titles, links = item.findall('title'), item.findall('link')
        if len(titles) != 1 or len(links) != 1 or len(titles[0]) or len(links[0]):
            continue
        title = ' '.join((titles[0].text or '').split())[:240]
        try:
            url = _destination((links[0].text or '').strip())
        except (ValueError, UnicodeError):
            continue
        if title and url not in {row['url'] for row in rows}:
            rows.append({'id': 'S' + str(len(rows) + 1), 'title': title, 'url': url})
    if not rows:
        raise RuntimeError('search_no_usable_results')
    return rows


def search_public(query, check, *, fetcher=fetch_resource, deadline=None):
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
        result = fetcher(ENDPOINT + '?q=' + quote_plus(query.strip()) + '&format=rss', guard,
                         kind='feed', allowed_origin=PROVIDER_ORIGIN, deadline=deadline)
    except OSError as exc:
        raise RuntimeError('search_transport_unavailable') from exc
    guard()
    if (result.get('status') != 200 or origin(result.get('url', '')) != PROVIDER_ORIGIN or
            result.get('mime') not in MIMES['feed']):
        raise RuntimeError('search_response_refused')
    rows = parse_feed(result.get('body'))
    guard()
    return rows
