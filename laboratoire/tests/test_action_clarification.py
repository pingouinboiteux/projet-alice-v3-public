import json
from unittest.mock import Mock
from intent_router import route

def test_ungrounded_level_is_clarified_instead_of_proposed():
    session=Mock();session.ask.return_value=(json.dumps({'kind':'volume','value':100,'reply':'Je remets le son.'}),0,{})
    action,reply=route(session,[{'role':'system','content':'Alice'}],'Remets le son du PC maintenant.')
    assert action.kind=='clarify'
    assert action.value is None
    assert reply.strip()

def test_valid_level_keeps_its_exact_value():
    session=Mock();session.ask.return_value=(json.dumps({'kind':'volume','value':35,'reply':'Proposition'}),0,{})
    action,_=route(session,[{'role':'system','content':'Alice'}],'Mets a trente-cinq pour cent.')
    assert (action.kind,action.value)==('volume',35)

def test_invalid_proposal_is_not_silently_replaced_with_free_dialogue():
    session=Mock();session.ask.return_value=('not JSON',0,{})
    action,reply=route(session,[{'role':'system','content':'Alice'}],'Une demande ambigue')
    assert action.kind=='clarify' and reply.strip()
