from unittest.mock import Mock,patch
import pytest
from public_navigation import PublicPage,read_rendered,canonical_url
from action_policy import parse
from intent_router import route

def test_command_and_url_canonicalization():
    assert parse('/voir https://example.org/page Quel tarif ?').kind=='web_observe'
    assert canonical_url('https://EXAMPLE.org:443#section')=='https://example.org/'
    with pytest.raises(ValueError):canonical_url('https://127.0.0.1/')

def test_router_cannot_invent_render_destination():
    session=Mock();session.ask.return_value=(' {"kind":"web_observe","value":"https://example.org/","reply":"ok"}',0,{})
    assert route(session,[{'role':'system','content':'Alice'}],'Observe une page')[0].kind=='clarify'

@pytest.mark.parametrize('method,kind,url',[('POST','script','https://example.org/a.js'),
    ('GET','xhr','https://example.org/data'),('GET','script','https://other.org/a.js'),
    ('GET','image','https://example.org/image.png'),('GET','document','https://example.org/other')])
def test_route_blocks_before_fetch(method,kind,url):
    fetcher=Mock();backend=PublicPage(lambda:None,fetcher=fetcher)
    backend.allowed_origin=('https','example.org',443);backend.target='https://example.org/'
    request=Mock(method=method,resource_type=kind,url=url)
    target=Mock(request=request);backend._route(target)
    target.abort.assert_called_once();fetcher.assert_not_called();target.fulfill.assert_not_called()

def test_resource_count_bound_before_fetch():
    backend=PublicPage(lambda:None,fetcher=Mock());backend.requests=20
    with pytest.raises(ValueError,match='count'):backend._fetch('https://example.org/a.js','script')
    backend.fetcher.assert_not_called()

def test_aggregate_budget_is_reserved_before_fetch():
    backend=PublicPage(lambda:None,fetcher=Mock());backend.bytes=3*1024*1024+1
    with pytest.raises(ValueError,match='total'):backend._fetch('https://example.org/a.js','script')
    backend.fetcher.assert_not_called()

def test_deadline_watchdog_stops_owned_browser_independently():
    backend=PublicPage(lambda:None,budget_seconds=.01)
    with patch.object(backend,'_fetch',side_effect=ValueError('fixture')), \
         patch('public_navigation.threading.Timer') as timer:
        with pytest.raises(ValueError):backend.start_url('https://example.org/')
        assert timer.call_args.args[1]==backend._expire
        timer.return_value.start.assert_called_once();timer.return_value.cancel.assert_called_once()

def test_render_changed_never_delivers_old_answer_and_closes():
    backend=Mock(target='https://example.org/',requests=1,bytes=50,blocked=0)
    snapshot={'revision':'one','text':'Tarif 17 euros.','truncated':False,'limitations':[]}
    backend.observe.return_value=snapshot;backend.current.return_value=False
    session=Mock(browser_demo=None)
    with patch('public_navigation.answer',return_value='OLD ANSWER'):
        result=read_rendered(session,backend.target,'Quel tarif ?',factory=lambda guard:backend)
    assert result['status']=='changed' and 'OLD ANSWER' not in result['reply']
    backend.close.assert_called_once();assert session.browser_demo is None

def test_cancellation_stops_before_startup_work():
    session=Mock(browser_demo=None);fetcher=Mock();created=[]
    def factory(guard):
        backend=PublicPage(guard,fetcher=fetcher);created.append(backend);return backend
    with pytest.raises(ValueError,match='cancelled'):
        read_rendered(session,'https://example.org/','?',factory=factory,cancelled=lambda:True)
    fetcher.assert_not_called()
    assert created[0].closed and session.browser_demo is None

def test_browser_exception_becomes_recoverable_turn_error():
    backend=Mock(timed_out=False);backend.start_url.side_effect=Exception('driver failed')
    with pytest.raises(RuntimeError,match='observee'):
        read_rendered(Mock(browser_demo=None),'https://example.org/','?',factory=lambda guard:backend)
    backend.close.assert_called_once()
