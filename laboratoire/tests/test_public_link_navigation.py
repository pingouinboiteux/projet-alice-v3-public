"""Candidate controller checks using fake pages; no actual browser or network."""
import copy
from unittest.mock import Mock,patch
import pytest
from public_link_navigation import read_linked

URL='https://example.org/start'
DEST='https://example.org/prices'

def setup():
    previous=object();session=Mock(browser_demo=previous)
    backend=Mock(target=URL)
    backend.page.url=URL
    data={'url':URL,'links':[{'label':'Tarifs','href':'/prices'}],'truncated':False}
    backend.page.evaluate.side_effect=lambda *args:copy.deepcopy(data)
    factory=Mock(return_value=backend)
    return session,backend,factory,previous,data

def test_one_hop_closed_before_reading_frozen_destination_and_restored():
    s,b,f,previous,data=setup()
    def read(session,url,question,**kwargs):
        b.close.assert_called_once();assert s.browser_demo is previous
        assert url==DEST and question=='Prix ?'
        assert kwargs['factory'] is f
        return {'status':'read','reply':'12 euros','url':DEST}
    with patch('public_link_navigation.read_rendered',side_effect=read) as reader:
        r=read_linked(s,URL,'Tarifs','Prix ?',source='voice',factory=f)
    assert r['hops']==1 and r['from_url']==URL and r['followed_url']==DEST
    reader.assert_called_once();b.page.click.assert_not_called()
    assert s.browser_demo is previous

@pytest.mark.parametrize('source',['twitch','discord','system',None])
def test_nonlocal_source_cannot_open_backend(source):
    s,b,f,previous,data=setup()
    with pytest.raises(ValueError):read_linked(s,URL,'Tarifs','Prix ?',source=source,factory=f)
    f.assert_not_called()

@pytest.mark.parametrize('label,question',[('', 'Prix ?'),(None,'Prix ?'),('x'*201,'Prix ?'),('Tarifs',''),('Tarifs','x'*2001)])
def test_invalid_local_request_rejected_before_factory(label,question):
    s,b,f,previous,data=setup()
    with pytest.raises(ValueError):read_linked(s,URL,label,question,factory=f)
    f.assert_not_called()

def test_cancelled_request_never_creates_backend():
    s,b,f,previous,data=setup()
    with pytest.raises(ValueError,match='cancelled'):read_linked(s,URL,'Tarifs','Prix ?',factory=f,cancelled=lambda:True)
    f.assert_not_called();assert s.browser_demo is previous

def test_missing_or_duplicate_link_closes_without_destination_read():
    for links in ([],[{'label':'Tarifs','href':'/prices'},{'label':'Tarifs','href':'/different'}]):
        s,b,f,previous,data=setup();data['links']=links
        with patch('public_link_navigation.read_rendered') as reader:
            assert read_linked(s,URL,'Tarifs','Prix ?',factory=f)['status']=='clarify'
        reader.assert_not_called();b.close.assert_called_once();assert s.browser_demo is previous

def test_unstable_links_never_select_or_read_destination():
    s,b,f,previous,data=setup();count=[0]
    def changing(*args):
        count[0]+=1;data['links'][0]['href']='/prices'+str(count[0]);return copy.deepcopy(data)
    b.page.evaluate.side_effect=changing
    with patch('public_link_navigation.read_rendered') as reader:
        assert read_linked(s,URL,'Tarifs','Prix ?',factory=f)['status']=='unstable'
    reader.assert_not_called();b.close.assert_called_once();assert s.browser_demo is previous

def test_final_freshness_check_prevents_changed_destination():
    s,b,f,previous,data=setup();count=[0]
    def changing(*args):
        count[0]+=1
        if count[0]==5:data['links'][0]['href']='/changed'
        return copy.deepcopy(data)
    b.page.evaluate.side_effect=changing
    with patch('public_link_navigation.read_rendered') as reader:
        assert read_linked(s,URL,'Tarifs','Prix ?',factory=f)['status']=='changed'
    reader.assert_not_called();b.close.assert_called_once();assert s.browser_demo is previous

def test_cancellation_after_first_close_prevents_second_page():
    s,b,f,previous,data=setup();stopped=[False]
    b.close.side_effect=lambda:stopped.__setitem__(0,True)
    with patch('public_link_navigation.read_rendered') as reader:
        with pytest.raises(ValueError,match='cancelled'):
            read_linked(s,URL,'Tarifs','Prix ?',factory=f,cancelled=lambda:stopped[0])
    reader.assert_not_called();assert s.browser_demo is previous

def test_failure_during_start_still_closes_and_restores():
    s,b,f,previous,data=setup();b.start_url.side_effect=OSError('failed')
    with pytest.raises(OSError):read_linked(s,URL,'Tarifs','Prix ?',factory=f)
    b.close.assert_called_once();assert s.browser_demo is previous

def test_failure_during_close_still_restores_session():
    s,b,f,previous,data=setup();b.close.side_effect=RuntimeError('close failed')
    with patch('public_link_navigation.read_rendered') as reader:
        with pytest.raises(RuntimeError,match='close failed'):read_linked(s,URL,'Tarifs','Prix ?',factory=f)
    reader.assert_not_called();assert s.browser_demo is previous

def test_destination_failure_does_not_retain_first_backend():
    s,b,f,previous,data=setup()
    with patch('public_link_navigation.read_rendered',side_effect=RuntimeError('destination failed')):
        with pytest.raises(RuntimeError,match='destination failed'):read_linked(s,URL,'Tarifs','Prix ?',factory=f)
    b.close.assert_called_once();assert s.browser_demo is previous
