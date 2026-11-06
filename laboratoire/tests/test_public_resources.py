"""No real network: transport behavior and DNS/TLS boundary via mocks."""
import io
import socket
import ssl
from email.message import Message
from unittest.mock import Mock,patch
import pytest
import public_resources as resources

def response(body=b'hello',status=200,mime='text/html',**headers):
    reply=Mock(status=status);reply.headers=Message()
    reply.headers['Content-Type']=mime
    for key,value in headers.items():reply.headers[key.replace('_','-')]=str(value)
    reply.getheader.side_effect=lambda name,default=None:reply.headers.get(name,default)
    reply.read1.side_effect=io.BytesIO(body).read1
    return reply

def transport(replies):
    connections=[]
    for reply in replies:
        connection=Mock();connection.getresponse.return_value=reply;connections.append(connection)
    return connections

def test_origin_canonical_and_invalid_origins():
    assert resources.origin('https://EXAMPLE.ORG.:443/path?q=1')==('https','example.org',443)
    for url in ['http://example.org/','https://127.0.0.1/','https://user:pw@example.org/','https://example.org:8443/']:
        with pytest.raises(ValueError):resources.origin(url)

def test_pinned_get_fixed_headers_and_charset_without_credentials():
    connections=transport([response(b'caf\xe9',mime='text/html; charset=iso-8859-1',Set_Cookie='secret=bad')])
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']) as dns,patch.object(resources,'PinnedHTTPS',side_effect=connections) as pinned:
        result=resources.fetch_resource('https://example.org/page?x=1#fragment',Mock())
    dns.assert_called_once_with('example.org')
    assert pinned.call_args.args[:2]==('example.org','8.8.8.8')
    args=connections[0].request.call_args
    assert args.args==('GET','/page?x=1')
    assert set(args.kwargs['headers'])=={'User-Agent','Accept','Accept-Encoding'}
    assert result['body']==b'caf\xe9' and result['content_type']=='text/html; charset=iso-8859-1'
    assert set(result)=={'url','mime','content_type','body','status'}
    connections[0].close.assert_called_once()

@pytest.mark.parametrize('kind,mime',[('document','application/xhtml+xml'),('document','text/plain'),('script','application/javascript'),('script','text/javascript'),('stylesheet','text/css')])
def test_allowed_resource_mimes(kind,mime):
    connections=transport([response(mime=mime)])
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']),patch.object(resources,'PinnedHTTPS',side_effect=connections):
        assert resources.fetch_resource('https://example.org/res',Mock(),kind=kind)['mime']==mime

@pytest.mark.parametrize('kind,reply',[
    ('script',response(mime='text/html')),('stylesheet',response(mime='text/plain')),
    ('document',response(mime='application/octet-stream')),
    ('document',response(Content_Encoding='gzip')),('document',response(Content_Disposition='attachment; filename=x')),
    ('document',response(Content_Length=resources.LIMIT+1)),('document',response(Content_Length='-1')),
    ('document',response(body=b'x'*(resources.LIMIT+1))),
])
def test_resource_refusals_close_connection(kind,reply):
    connections=transport([reply])
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']),patch.object(resources,'PinnedHTTPS',side_effect=connections),pytest.raises(ValueError):
        resources.fetch_resource('https://example.org/res',Mock(),kind=kind)
    connections[0].close.assert_called_once()

@pytest.mark.parametrize('location',['https://127.0.0.1/','http://example.org/','https://other.org/'])
def test_redirect_refused_before_next_connection(location):
    connections=transport([response(status=302,Location=location)])
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']) as dns,patch.object(resources,'PinnedHTTPS',side_effect=connections) as pinned,pytest.raises(ValueError):
        resources.fetch_resource('https://example.org/',Mock(),allowed_origin=resources.origin('https://example.org/'))
    assert pinned.call_count==1 and dns.call_count==1

def test_dns_revalidated_and_rebound_private_address_refused():
    connections=transport([response(status=302,Location='/next')])
    rows=lambda address:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]
    with patch('web_reader.socket.getaddrinfo',side_effect=[rows('8.8.8.8'),rows('127.0.0.1')]) as dns,patch.object(resources,'PinnedHTTPS',side_effect=connections) as pinned,pytest.raises(ValueError):
        resources.fetch_resource('https://example.org/',Mock())
    assert dns.call_count==2 and pinned.call_count==1

def test_exactly_four_redirects_allowed_and_fifth_refused():
    for redirects,success in [(4,True),(5,False)]:
        connections=transport([response(status=302,Location='/next') for _ in range(redirects)]+[response()])
        with patch.object(resources,'public_addresses',return_value=['8.8.8.8']),patch.object(resources,'PinnedHTTPS',side_effect=connections) as pinned:
            if success:assert resources.fetch_resource('https://example.org/',Mock())['status']==200
            else:
                with pytest.raises(ValueError,match='redirect_limit'):resources.fetch_resource('https://example.org/',Mock())
        assert pinned.call_count==5

def test_tls_verification_error_propagates_no_retry_or_bypass():
    connection=Mock();connection.request.side_effect=ssl.SSLCertVerificationError('invalid certificate')
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']),patch.object(resources,'PinnedHTTPS',return_value=connection) as pinned,pytest.raises(ssl.SSLCertVerificationError):
        resources.fetch_resource('https://example.org/',Mock())
    assert pinned.call_count==1;connection.close.assert_called_once()

def test_expired_deadline_and_guard_fail_before_network():
    with patch.object(resources,'PinnedHTTPS') as pinned,pytest.raises(TimeoutError):
        resources.fetch_resource('https://example.org/',Mock(),deadline=0)
    pinned.assert_not_called()
    with patch.object(resources,'PinnedHTTPS') as pinned,pytest.raises(RuntimeError,match='FPS'):
        resources.fetch_resource('https://example.org/',Mock(side_effect=RuntimeError('FPS')))
    pinned.assert_not_called()

def test_read_crossing_deadline_fails_instead_of_returning_data():
    reply=response();now=[0]
    def read(size):now[0]=26;return b'hello'
    reply.read1.side_effect=read
    connections=transport([reply])
    with patch.object(resources,'public_addresses',return_value=['8.8.8.8']),patch.object(resources,'PinnedHTTPS',side_effect=connections),patch.object(resources.time,'monotonic',side_effect=lambda:now[0]),pytest.raises(TimeoutError):
        resources.fetch_resource('https://example.org/',Mock())
    connections[0].close.assert_called_once()
