from unittest.mock import Mock
from link_dialogue import LinkDialogue

REQUEST='Suis le lien Tarifs sur https://example.org et trouve le prix adulte.'
TARGET={'url':'https://example.org','label':'Tarifs','question':'le prix adulte'}

def setup():
    now=[0.];s=Mock();planner=Mock(return_value={'status':'ready','target':TARGET})
    reader=Mock(return_value={'status':'read','reply':'Extrait public','url':'https://example.org/prices'})
    return LinkDialogue(s,planner=planner,reader=reader,clock=lambda:now[0]),planner,reader,now

def test_request_uses_only_local_turns_and_clears_after_read():
    c,p,r,now=setup()
    assert c.can_handle(REQUEST)
    assert c.handle(REQUEST,'voice')['status']=='read'
    assert p.call_args.args[1]==[REQUEST]
    assert r.call_args.args[1:]==tuple(TARGET.values())
    assert c.turns==[]

def test_missing_field_then_completion_retains_only_local_request():
    c,p,r,now=setup();p.return_value={'status':'clarify'}
    assert c.handle(REQUEST,'voice')['status']=='clarify'
    assert c.can_handle('La question est Quel prix ?')
    p.return_value={'status':'ready','target':TARGET}
    c.handle('La question est Quel prix ?','voice')
    assert p.call_args.args[1]==[REQUEST,'La question est Quel prix ?']

def test_page_suggestions_never_enter_intent_parser():
    c,p,r,now=setup();r.return_value={'status':'clarify','reply':'PAGE_SENTINEL','choices':['PAGE_SENTINEL']}
    c.handle(REQUEST,'voice')
    assert c.can_handle('Le lien est Horaires')
    c.handle('Le lien est Horaires','voice')
    assert 'PAGE_SENTINEL' not in repr(p.call_args)

def test_expiry_unrelated_and_cancellation_clear_request():
    c,p,r,now=setup();p.return_value={'status':'clarify'}
    c.handle(REQUEST,'voice');now[0]=301
    assert not c.can_handle('Le lien est Tarifs')
    assert not c.turns
    c.handle(REQUEST,'voice');assert not c.can_handle('Bonjour')
    c.cancel();assert not c.turns
    c.handle(REQUEST,'voice');p.return_value={'status':'cancel'}
    assert c.handle('annule','voice')['status']=='cancelled'
    r.assert_not_called();assert not c.turns

def test_interrupt_during_model_does_not_read():
    c,p,r,now=setup();stopped=[False]
    def plan(*args):stopped[0]=True;return {'status':'ready','target':TARGET}
    p.side_effect=plan
    assert c.handle(REQUEST,'voice',cancelled=lambda:stopped[0])['status']=='cancelled'
    r.assert_not_called()

def test_failed_browser_is_reported_and_next_request_can_work():
    c,p,r,now=setup();r.side_effect=RuntimeError('network failure')
    assert c.handle(REQUEST,'voice')['status']=='failed'
    assert not c.turns
    r.side_effect=None
    assert c.handle(REQUEST,'voice')['status']=='read'

def test_sources_are_checked_before_planning_or_reading():
    import pytest
    c,p,r,now=setup()
    with pytest.raises(ValueError):c.handle(REQUEST,'twitch')
    p.assert_not_called();r.assert_not_called()

def test_router_proposal_never_substitutes_model_text_for_user_request():
    from intent_router import route
    s=Mock();s.ask.return_value=('{"kind":"web_follow","value":"invented URL and label","reply":"proposition"}',0,{})
    action,_=route(s,[{'role':'system','content':'validation'}],REQUEST)
    assert action.kind=='web_follow' and action.value==REQUEST

def test_nonrequest_from_router_does_not_reach_model_or_browser():
    c,p,r,now=setup()
    assert c.handle('Par exemple '+REQUEST,'text')['status']=='clarify'
    p.assert_not_called();r.assert_not_called()

def test_existing_clarification_is_cancelled_before_a_new_direct_request():
    c,p,r,now=setup();p.return_value={'status':'clarify'}
    c.handle(REQUEST,'voice')
    next_request='Suis le lien Horaires sur https://example.org et trouve les horaires.'
    c.handle(next_request,'voice')
    assert p.call_args.args[1]==[next_request]
