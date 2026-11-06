"""Bounded rendered HTTPS reading; isolated profile and mediated network only."""
import html
import socket
import time
import threading
from email.message import Message
from urllib.parse import urlsplit,urlunsplit,quote
from observer_browser import BrowserDemo
from public_resources import fetch_resource,origin
from rendered_observation import observe_page,check_snapshot
from web_passages import select_passages
from web_evidence import answer

CSP=("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
     "connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; frame-src 'none'; "
     "object-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'")

def canonical_url(url):
    _,host,_=origin(url);parts=urlsplit(url)
    return urlunsplit(('https',host,quote(parts.path or '/',safe='/%:@!$&()*+,;=-._~'),
                      quote(parts.query,safe='%&=/:?@!$()*+,;~-._'),''))

class PublicPage(BrowserDemo):
    def __init__(self,guard,*,fetcher=fetch_resource,budget_seconds=35):
        super().__init__(guard)
        if type(budget_seconds) not in (int,float) or not 0<budget_seconds<=35:raise ValueError('invalid_navigation_budget')
        self.budget_seconds=budget_seconds;self._watchdog=None;self.timed_out=False
        self.fetcher=fetcher;self.target=None;self.allowed_origin=None
        self.deadline=None;self.requests=0;self.bytes=0;self.blocked=0
        self._proxy_socket=None;self._document_served=False;self.document=None

    def _browser_args(self):
        return super()._browser_args()+['--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--dns-prefetch-disable']

    def _expire(self):
        self.timed_out=True
        self.stop_owned()

    def _check(self):
        self.guard()
        if self.deadline is not None and time.monotonic()>self.deadline:
            raise TimeoutError('public_navigation_deadline')

    def _fetch(self,url,kind):
        self._check()
        if self.requests>=20:raise ValueError('public_resource_count_limit')
        # Reserve the transport's maximum response before beginning the request.
        if self.bytes+1024*1024>4*1024*1024:raise ValueError('public_resource_total_limit')
        self.requests+=1
        resource=self.fetcher(url,self._check,kind=kind,allowed_origin=self.allowed_origin,deadline=self.deadline)
        self.bytes+=len(resource['body'])
        if self.bytes>4*1024*1024:raise ValueError('public_resource_total_limit')
        self._check();return resource

    def _route(self,route):
        try:
            self._check();request=route.request
            if request.method!='GET' or origin(request.url)!=self.allowed_origin:
                raise ValueError('public_request_refused')
            if request.resource_type=='document':
                if self._document_served or request.url!=self.target or request.frame!=self.page.main_frame:
                    raise ValueError('public_navigation_refused')
                self._document_served=True;resource=self.document
            else:
                kind={'script':'script','stylesheet':'stylesheet'}.get(request.resource_type)
                if kind is None:raise ValueError('public_resource_type_refused')
                resource=self._fetch(request.url,kind)
            headers={'Content-Type':resource.get('content_type',resource['mime']),'Cache-Control':'no-store',
                     'Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff',
                     'Referrer-Policy':'no-referrer'}
            route.fulfill(status=200,headers=headers,body=resource['body'])
        except Exception:
            self.blocked+=1
            route.abort()

    def start_url(self,url):
        url=canonical_url(url)
        self.allowed_origin=origin(url)
        self.deadline=time.monotonic()+self.budget_seconds
        self._watchdog=threading.Timer(self.budget_seconds,self._expire)
        self._watchdog.daemon=True;self._watchdog.start()
        try:
            self.document=self._fetch(url,'document');self.target=canonical_url(self.document['url'])
            if self.document['mime']=='text/plain':
                content_type=Message();content_type['content-type']=self.document.get('content_type','text/plain')
                text=self.document['body'].decode(content_type.get_content_charset() or 'utf-8',errors='replace')
                self.document={**self.document,'mime':'text/html','content_type':'text/html; charset=utf-8','body':('<meta charset="utf-8"><pre>'+html.escape(text)+'</pre>').encode()}
            super().start()
            self.context.close()
            # A bound, non-listening local port is reserved for a dead proxy.
            # Browser networking cannot bypass Python's pinned HTTPS transport.
            self._proxy_socket=socket.socket();self._proxy_socket.bind(('127.0.0.1',0))
            port=self._proxy_socket.getsockname()[1]
            self.context=self.browser.new_context(viewport={'width':1100,'height':800},
                service_workers='block',accept_downloads=False,permissions=[],
                proxy={'server':f'http://127.0.0.1:{port}','bypass':'<-loopback>'})
            self.context.route('**/*',self._route)
            self.context.route_web_socket('**/*',lambda ws:ws.close())
            self.page=self.context.new_page()
            self.context.on('page',lambda page:page.close() if page!=self.page else None)
            self.page.set_default_timeout(3000)
            self.page.goto(self.target,wait_until='load',timeout=15000)
            self._check()
            if self.page.url!=self.target:raise ValueError('public_scope_changed')
            return self
        except BaseException:
            self.close();raise

    def observe(self):
        return observe_page(self.page,self._check,expected_url=self.target)

    def current(self,snapshot):
        return check_snapshot(self.page,self._check,snapshot,max_age=10,expected_url=self.target)

    def close(self):
        if self._watchdog is not None:self._watchdog.cancel()
        try:super().close()
        finally:
            if self._proxy_socket is not None:self._proxy_socket.close();self._proxy_socket=None

def read_rendered(session,url,question,*,factory=PublicPage,cancelled=lambda:False):
    def guard():
        session.check()
        if cancelled():raise ValueError('public_read_cancelled')
    backend=factory(guard)
    previous=getattr(session,'browser_demo',None)
    session.browser_demo=backend
    try:
        backend.start_url(url)
        before=backend.observe()
        # Bounded settling detects continuing changes; it does not promise that
        # every delayed resource has arrived on an arbitrary website.
        stable=False;unchanged=0
        for _ in range(10):
            guard();backend.page.wait_for_timeout(150)
            after=backend.observe()
            unchanged=unchanged+1 if after['revision']==before['revision'] else 0
            if unchanged>=3:stable=True;break
            before=after
        if not stable:return {'status':'unstable','reply':'La page change encore. Je ne peux pas confirmer une lecture stable.'}
        source={'url':backend.target,'title':'Page publique observee',**select_passages(after['text'],question[:2000])}
        # Resource restrictions make this a partial view even when all observed
        # text fits; CSP may block resources before request routing sees them.
        source['truncated']=True
        reply=answer(session,question,source)
        guard()
        if not backend.current(after):return {'status':'changed','reply':'La page a change pendant ma lecture. Je ne peux pas confirmer cet extrait.'}
        return {'status':'read','reply':reply,'url':backend.target,'partial':source['truncated'],
                'requests':backend.requests,'blocked':backend.blocked,'bytes':backend.bytes}
    except Exception as error:
        if getattr(backend,'timed_out',False) is True:
            raise RuntimeError('Delai de lecture atteint. Le navigateur isole a ete arrete.') from error
        if isinstance(error,(ValueError,RuntimeError,OSError)):raise
        raise RuntimeError('La page n a pas pu etre observee ('+type(error).__name__+').') from error
    finally:
        try:backend.close()
        finally:session.browser_demo=previous
