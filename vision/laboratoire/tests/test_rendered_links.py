"""Synthetic link observations; no browser, model, personal data or network."""
import copy
from unittest.mock import Mock
import pytest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from vision.laboratoire.rendered_links import observe_links, links_current, select_link, LINKS_JS

URL='https://example.org/start'

def payload(href='/prices',label='Tarifs'):
    return {'url':URL,'links':[{'label':label,'href':href}],'truncated':False}

def page(data=None):
    data=payload() if data is None else data
    return Mock(url=URL,evaluate=Mock(side_effect=lambda script,url:copy.deepcopy(data)))

def test_snapshot_bound_to_explicit_url_guarded_and_exact():
    p=page();guard=Mock()
    result=observe_links(p,guard,expected_url=URL,clock=lambda:10.)
    assert result['links']==payload()['links'] and result['observed_at']==10.
    p.evaluate.assert_called_once_with(LINKS_JS,URL)
    assert guard.call_count==2
    assert links_current(p,guard,result,expected_url=URL,clock=lambda:11.)

@pytest.mark.parametrize('href,expected',[
    ('/prices','https://example.org/prices'),
    ('prices','https://example.org/prices'),
    ('/prices#hours','https://example.org/prices'),
    ('https://EXAMPLE.org:443/prices','https://example.org/prices'),
    ('?view=prices','https://example.org/start?view=prices'),
])
def test_only_observed_href_resolves(href,expected):
    assert select_link(payload(href),'  TARIFS ')==expected

@pytest.mark.parametrize('href',[
    'https://other.example/prices','//other.example/prices',
    'http://example.org/prices','javascript:alert(1)','data:text/html,test',
    'file:///test','https://127.0.0.1/prices','https://localhost/prices',
    'https://user:pass@example.org/prices','https://example.org:444/prices',
    '#prices','/start','/start#prices','/pri\nces',
])
def test_unsafe_cross_origin_or_same_page_destinations_rejected(href):
    with pytest.raises(ValueError):select_link(payload(href),'Tarifs')

def test_labels_are_exact_not_model_generated_or_substring_matches():
    with pytest.raises(ValueError):select_link(payload(),'Tarif')
    with pytest.raises(ValueError):select_link(payload(),'Clique le premier')
    with pytest.raises(ValueError):select_link(payload(),None)

def test_downloads_stay_in_inventory_to_detect_ambiguous_labels():
    data=payload();data['links'][0]['download']=True
    with pytest.raises(ValueError,match='download'):select_link(data,'Tarifs')
    data['links'].append({'label':'Tarifs','href':'/normal'})
    with pytest.raises(ValueError,match='ambiguous'):select_link(data,'Tarifs')

def test_empty_href_duplicate_is_not_discarded():
    data=payload();data['links'].append({'label':'Tarifs','href':''})
    with pytest.raises(ValueError,match='ambiguous'):select_link(data,'Tarifs')

def test_duplicate_labels_and_truncated_inventory_rejected():
    data=payload();data['links'].append({'label':'tarifs','href':'/another'})
    with pytest.raises(ValueError,match='ambiguous'):select_link(data,'Tarifs')
    data=payload();data['truncated']=True
    with pytest.raises(ValueError,match='incomplete'):select_link(data,'Tarifs')

@pytest.mark.parametrize('now',[9.,20.01,float('nan'),float('inf'),True])
def test_stale_future_or_invalid_clock_rejected_without_dom_read(now):
    p=page();snapshot=observe_links(p,Mock(),expected_url=URL,clock=lambda:10.)
    p.evaluate.reset_mock()
    assert not links_current(p,Mock(),snapshot,expected_url=URL,clock=lambda:now)
    p.evaluate.assert_not_called()

def test_changed_destination_or_label_invalidates_snapshot():
    data=payload();p=page(data)
    snapshot=observe_links(p,Mock(),expected_url=URL,clock=lambda:10.)
    data['links'][0]['href']='/changed'
    assert not links_current(p,Mock(),snapshot,expected_url=URL,clock=lambda:11.)
    data['links'][0]['href']='/prices';data['links'][0]['label']='Different'
    assert not links_current(p,Mock(),snapshot,expected_url=URL,clock=lambda:11.)

def test_caller_mutation_is_rejected_before_page_read():
    p=page();snapshot=observe_links(p,Mock(),expected_url=URL,clock=lambda:10.)
    snapshot['links'][0]['href']='/invented';p.evaluate.reset_mock()
    assert not links_current(p,Mock(),snapshot,expected_url=URL,clock=lambda:11.)
    p.evaluate.assert_not_called()

def test_scope_change_before_or_during_observation_is_rejected():
    p=page();p.url='https://other.example/'
    with pytest.raises(ValueError):observe_links(p,Mock(),expected_url=URL)
    p.evaluate.assert_not_called()
    p=page()
    def mutate(script,url):p.url='https://other.example/';return payload()
    p.evaluate.side_effect=mutate
    with pytest.raises(ValueError):observe_links(p,Mock(),expected_url=URL)

@pytest.mark.parametrize('data',[
    {'url':URL,'links':[],'truncated':False,'extra':1},
    {'url':URL,'links':[{'label':'x','href':'/a','onclick':'run'}],'truncated':False},
    {'url':URL,'links':[{'label':'x'*1001,'href':'/a'}],'truncated':False},
    {'url':URL,'links':[{'label':'x','href':'a'*2049}],'truncated':False},
    {'url':URL,'links':[],'truncated':0},
    {'url':URL,'links':[{'label':'x','href':'/a'}]*101,'truncated':False},
])
def test_malformed_payload_refused(data):
    with pytest.raises(ValueError):observe_links(page(data),Mock(),expected_url=URL)

def test_guard_failure_is_never_swallowed():
    p=page();guard=Mock(side_effect=RuntimeError('FPS'))
    with pytest.raises(RuntimeError,match='FPS'):observe_links(p,guard,expected_url=URL)
    p.evaluate.assert_not_called()


@pytest.mark.parametrize('length', [201, 1000])
def test_long_observed_label_preserves_short_links_without_becoming_selectable(length):
    data=payload();long_label='x'*length
    data['links'].append({'label':long_label,'href':'/long-card'})
    snapshot=observe_links(page(data),Mock(),expected_url=URL)
    assert not snapshot['truncated']
    assert snapshot['links']==data['links']
    assert select_link(snapshot,'Tarifs')=='https://example.org/prices'
    with pytest.raises(ValueError,match='explicit_link_label_required'):
        select_link(snapshot,long_label)


def test_long_observed_label_still_participates_in_duplicate_detection():
    data=payload()
    data['links'].append({'label':' ' * 201 + 'Tarifs','href':'/different'})
    snapshot=observe_links(page(data),Mock(),expected_url=URL)
    with pytest.raises(ValueError,match='ambiguous'):
        select_link(snapshot,'Tarifs')


def test_truncation_from_oversized_label_still_blocks_other_links():
    # JS skips the >1000 character label and marks the whole inventory incomplete.
    data=payload();data['truncated']=True
    snapshot=observe_links(page(data),Mock(),expected_url=URL)
    with pytest.raises(ValueError,match='incomplete'):
        select_link(snapshot,'Tarifs')
