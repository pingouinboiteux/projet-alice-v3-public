"""Fake page only. Real Chromium/model qualification belongs to the parent bench."""
import copy
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from vision.laboratoire.rendered_observation import observe_page,check_snapshot,MAX_TEXT,MAX_BLOCKS,OBSERVE_RENDERED

def payload():
    return {'url':'about:blank','text':'Tarif : 17 euros.',
        'blocks':[{'text':'Tarif : 17 euros.','role':'paragraph',
            'bounds':{'x':0,'y':12,'width':140,'height':18},'in_viewport':True}],
        'truncated':False,'limitations':['occlusion_and_complex_clipping_not_resolved']}

def page(value=None):
    value=payload() if value is None else value
    return Mock(url='about:blank',evaluate=Mock(side_effect=lambda script,url:copy.deepcopy(value)))

def test_snapshot_keeps_geometry_text_time_and_guard():
    guard=Mock();target=page()
    result=observe_page(target,guard,clock=lambda:10)
    assert result['text']=='Tarif : 17 euros.' and result['observed_at']==10
    assert result['blocks'][0]['bounds']['height']==18
    assert len(result['revision'])==64 and guard.call_count==2
    assert check_snapshot(target,guard,result,clock=lambda:11)

@pytest.mark.parametrize('age',[-1,2.01,float('inf')])
def test_stale_or_future_snapshot_is_refused_without_dom_read(age):
    target=page();snapshot=observe_page(target,Mock(),clock=lambda:10)
    target.evaluate.reset_mock()
    assert not check_snapshot(target,Mock(),snapshot,clock=lambda:10+age)
    target.evaluate.assert_not_called()

def test_text_change_and_geometry_change_are_detected():
    data=payload();target=page(data);snapshot=observe_page(target,Mock(),clock=lambda:10)
    data['blocks'][0]['bounds']['y']=40
    assert not check_snapshot(target,Mock(),snapshot,clock=lambda:11)
    data['blocks'][0]['bounds']['y']=12
    data['text']=data['blocks'][0]['text']='Tarif : 23 euros.'
    assert not check_snapshot(target,Mock(),snapshot,clock=lambda:11)

def test_modified_caller_snapshot_rejected_before_read():
    target=page();snapshot=observe_page(target,Mock(),clock=lambda:10)
    snapshot['text']=snapshot['blocks'][0]['text']='Faux texte'
    target.evaluate.reset_mock()
    assert not check_snapshot(target,Mock(),snapshot,clock=lambda:11)
    target.evaluate.assert_not_called()

def test_guard_failures_propagate_before_and_after_read():
    target=page();guard=Mock(side_effect=RuntimeError('FPS guard'))
    with pytest.raises(RuntimeError,match='FPS'):observe_page(target,guard)
    target.evaluate.assert_not_called()
    guard=Mock(side_effect=[None,RuntimeError('RAM guard')])
    with pytest.raises(RuntimeError,match='RAM'):observe_page(target,guard)

def test_navigation_during_observation_is_refused():
    target=page()
    def change(script,url):target.url='https://example.org/';return payload()
    target.evaluate.side_effect=change
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock())

def test_scope_and_reported_scope_must_both_be_blank():
    target=page();target.url='file:///private'
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock())
    target=page({**payload(),'url':'https://example.org/'})
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock())

@pytest.mark.parametrize('modify',[
    lambda v:v.update(text='x'*(MAX_TEXT+1)),
    lambda v:v.update(blocks=v['blocks']*(MAX_BLOCKS+1)),
    lambda v:v['blocks'][0]['bounds'].update(x=float('nan')),
    lambda v:v['blocks'][0]['bounds'].update(width=-1),
    lambda v:v['blocks'][0].update(in_viewport=1),
    lambda v:v.update(text='Does not match blocks'),
    lambda v:v.update(truncated='yes'),
    lambda v:v.update(limitations=['x'*101]),
])
def test_malformed_or_unbounded_snapshot_rejected(modify):
    value=payload();modify(value)
    with pytest.raises(ValueError):observe_page(page(value),Mock())

def test_truncation_and_unread_features_remain_visible_to_caller():
    value=payload();value.update(truncated=True,limitations=['frames_not_read','canvas_not_read','shadow_dom_not_read'])
    result=observe_page(page(value),Mock())
    assert result['truncated'] and 'frames_not_read' in result['limitations']

def test_check_accounts_for_time_spent_reobserving():
    target=page();snapshot=observe_page(target,Mock(),clock=lambda:10)
    stamps=iter([11,11,13])
    assert not check_snapshot(target,Mock(),snapshot,max_age=2,clock=lambda:next(stamps))

def test_snapshot_clock_must_be_finite():
    with pytest.raises(ValueError,match='clock'):observe_page(page(),Mock(),clock=lambda:float('nan'))


def bound_page(url):
    data={**payload(),'url':url}
    target=page(data);target.url=url
    return target,data


@pytest.mark.parametrize('url',['https://example.org/article','https://example.org/article#section'])
def test_public_page_requires_explicit_exact_url_and_passes_it_to_js(url):
    target,data=bound_page(url)
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock())
    snapshot=observe_page(target,Mock(),clock=lambda:10,expected_url=url)
    assert snapshot['url']==url
    target.evaluate.assert_called_once_with(OBSERVE_RENDERED,url)
    assert 'location.href !== expectedUrl' in OBSERVE_RENDERED
    assert check_snapshot(target,Mock(),snapshot,clock=lambda:11,expected_url=url)
    assert not check_snapshot(target,Mock(),snapshot,clock=lambda:11)


@pytest.mark.parametrize('url',[None,'file:///private','http://example.org/',
    'https://127.0.0.1/','https://account:secret@example.org/','https://host.local/'])
def test_invalid_expected_url_never_reaches_dom(url):
    target=page();target.url=url
    with pytest.raises(ValueError):observe_page(target,Mock(),expected_url=url)
    target.evaluate.assert_not_called()
    assert not check_snapshot(target,Mock(),{},expected_url=url)


@pytest.mark.parametrize('actual',['https://other.example.org/article',
    'https://example.org/other','https://example.org/article#other'])
def test_same_page_and_reported_url_cannot_rebind_expected_scope(actual):
    target,_=bound_page(actual)
    with pytest.raises(ValueError,match='scope'):
        observe_page(target,Mock(),expected_url='https://example.org/article')
    target.evaluate.assert_not_called()


def test_reported_url_and_navigation_during_public_observation_are_checked():
    expected='https://example.org/article'
    target,data=bound_page(expected)
    data['url']='https://example.org/other'
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock(),expected_url=expected)
    target,data=bound_page(expected)
    def navigate(script,url):
        target.url='https://other.example.org/'
        return copy.deepcopy(data)
    target.evaluate.side_effect=navigate
    with pytest.raises(ValueError,match='scope'):observe_page(target,Mock(),expected_url=expected)


def test_https_snapshot_recheck_does_not_follow_navigation():
    expected='https://example.org/article'
    target,_=bound_page(expected)
    snapshot=observe_page(target,Mock(),clock=lambda:10,expected_url=expected)
    target.url='https://example.org/other'
    target.evaluate.reset_mock()
    with pytest.raises(ValueError,match='scope'):
        check_snapshot(target,Mock(),snapshot,clock=lambda:11,expected_url=expected)
    target.evaluate.assert_not_called()


@pytest.mark.parametrize('legacy_first', [True, False])
def test_legacy_and_component_imports_share_one_module(tmp_path, legacy_first):
    """Fresh interpreters also cover launches outside the repository root."""
    import subprocess
    script = """
import sys
sys.path.insert(0, sys.argv[1])
if sys.argv[2] == 'True':
    import rendered_observation as legacy
    from vision.laboratoire import rendered_observation as current
else:
    from vision.laboratoire import rendered_observation as current
    sys.path.insert(0, sys.argv[3])
    import rendered_observation as legacy
assert legacy is current
assert legacy._validate is current._validate
assert legacy.observe_page is current.observe_page
from action_policy import validate_url
assert current.validate_url is validate_url
assert current._expected_url('https://example.org/') == 'https://example.org/'
"""
    scripts = ROOT / 'laboratoire/scripts'
    result = subprocess.run(
        [sys.executable, '-I', '-c', script, str(scripts if legacy_first else ROOT),
         str(legacy_first), str(scripts)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
