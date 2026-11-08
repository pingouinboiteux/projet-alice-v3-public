"""Pinned, bounded public HTTPS resources for a browser with direct network denied.

Only this transport performs GETs. Browser cookies, authorization, referer and
request headers are never forwarded. Callers enforce their aggregate budget.
"""
import math
import re
import time
from urllib.parse import urlsplit, urljoin
from action_policy import validate_url
from web_reader import public_addresses, PinnedHTTPS

LIMIT=1024*1024
MIMES={
    'feed':frozenset({'text/xml','application/xml','application/rss+xml'}),
    'document':frozenset({'text/html','application/xhtml+xml','text/plain'}),
    'script':frozenset({'text/javascript','application/javascript','application/ecmascript','text/ecmascript'}),
    'stylesheet':frozenset({'text/css'}),
}

def origin(url):
    """Canonical public HTTPS origin, without DNS resolution."""
    if type(url) is not str:raise ValueError('resource_url_required')
    validate_url(url)
    parsed=urlsplit(url)
    host=parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
    return ('https',host,443)

def fetch_resource(url,check,*,kind='document',allowed_origin=None,deadline=None):
    """Read up to1MiB through a validated/pinned address, at most4 redirects.

    Returns url,mime,content_type,body,status. content_type preserves a bounded
    charset for byte-for-byte browser fulfilment; response headers are discarded.
    The shared deadline can shorten but never extend the25 second local budget.
    """
    if kind not in MIMES or not callable(check):raise ValueError('invalid_resource_request')
    if allowed_origin is not None and (type(allowed_origin) is not tuple or len(allowed_origin)!=3
            or allowed_origin[0]!='https' or type(allowed_origin[1]) is not str or allowed_origin[2]!=443):
        raise ValueError('invalid_allowed_origin')
    now=time.monotonic()
    if deadline is not None and (type(deadline) not in (int,float) or not math.isfinite(deadline)):
        raise ValueError('invalid_resource_deadline')
    end=min(now+25,deadline) if deadline is not None else now+25
    def guard():
        check()
        remaining=end-time.monotonic()
        if remaining<=0:raise TimeoutError('resource_deadline_exceeded')
        return remaining
    for hop in range(5):
        guard()
        current_origin=origin(url)
        if allowed_origin is not None and current_origin!=allowed_origin:
            raise ValueError('resource_origin_changed')
        parsed=urlsplit(url)
        address=public_addresses(current_origin[1])[0]
        remaining=guard()
        connection=PinnedHTTPS(current_origin[1],address,min(8,remaining))
        try:
            target=parsed.path or '/'
            if parsed.query:target+='?'+parsed.query
            connection.request('GET',target,headers={
                'User-Agent':'AliceLab/1.0 (public read-only observer)',
                'Accept':', '.join(sorted(MIMES[kind])),
                'Accept-Encoding':'identity',
            })
            remaining=guard()
            if connection.sock is not None:connection.sock.settimeout(min(8,remaining))
            response=connection.getresponse();guard()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise ValueError('resource_redirect_without_location')
                if hop==4:raise ValueError('resource_redirect_limit')
                url=urljoin(url,location)
                continue
            if response.status!=200:raise RuntimeError('resource_http_status_'+str(response.status))
            mime=response.headers.get_content_type()
            if mime not in MIMES[kind]:raise ValueError('resource_mime_refused')
            if response.getheader('Content-Encoding','identity').strip().lower()!='identity':
                raise ValueError('resource_encoding_refused')
            if 'attachment' in response.getheader('Content-Disposition','').lower():
                raise ValueError('resource_attachment_refused')
            size=response.getheader('Content-Length')
            if size is not None and (not re.fullmatch(r'[0-9]+',size.strip()) or int(size)>LIMIT):
                raise ValueError('resource_size_refused')
            parts=[];size=0
            while True:
                remaining=guard()
                if connection.sock is not None:connection.sock.settimeout(min(8,remaining))
                data=response.read1(min(16384,LIMIT+1-size))
                guard()
                if not data:break
                size+=len(data)
                if size>LIMIT:raise ValueError('resource_size_refused')
                parts.append(data)
            charset=response.headers.get_content_charset()
            content_type=mime
            if charset:
                if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',charset):raise ValueError('resource_charset_refused')
                content_type+='; charset='+charset
            return {'url':url,'mime':mime,'content_type':content_type,'body':b''.join(parts),'status':200}
        finally:
            connection.close()
    raise ValueError('resource_redirect_limit')
