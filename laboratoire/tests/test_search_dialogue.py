from unittest.mock import Mock
import pytest
from search_dialogue import SearchDialogue

TEXT='/rechercher horaires du Louvre'

def controller(**kwargs):
    return SearchDialogue(Mock(),planner=Mock(return_value={'status':'clarify'}),reader=Mock(),**kwargs)

def test_expiration():
    now=[0];c=controller(clock=lambda:now[0]);c.handle(TEXT,'text')
    assert c.can_handle('La question est prix Louvre')
    now[0]=300
    assert not c.can_handle('La question est prix Louvre') and not c.turns

def test_turn_limit():
    c=controller();c.handle(TEXT,'text')
    for i in range(8):c.handle('La question est météo','text')
    assert not c.turns;c.reader.assert_not_called()

def test_cancel_before_reader():
    c=controller();r=c.handle(TEXT,'text',cancelled=lambda:True)
    assert r['status']=='cancelled';c.planner.assert_not_called();c.reader.assert_not_called()

@pytest.mark.parametrize('source',['page','twitch','discord'])
def test_external_rejected(source):
    c=controller()
    with pytest.raises(ValueError):c.handle(TEXT,source)
    c.planner.assert_not_called()

def test_ready_reader_gets_exact_query_and_clears():
    reader=Mock(return_value={'status':'found','reply':'Verifie','sources':['https://example.org']})
    c=SearchDialogue(Mock(),planner=Mock(return_value={'status':'ready','target':{'question':'horaires du Louvre'}}),reader=reader)
    assert c.handle(TEXT,'voice')['status']=='found'
    assert reader.call_args.args[1]=='horaires du Louvre' and not c.turns


def routed_controller(decision='execute',**kwargs):
    import json
    session=Mock()
    session.ask.return_value=(json.dumps({'decision':decision}),0,0)
    reader=Mock(return_value={'status':'found','reply':'Extrait verifie'})
    return SearchDialogue(session,reader=reader,**kwargs)


def test_routed_request_still_requires_real_planner_and_exact_text():
    text='Quel est le tarif du Louvre aujourd hui ?'
    c=routed_controller()
    assert c.handle(text,'text',routed=True)['status']=='found'
    assert c.reader.call_args.args[1]==text
    c.session.ask.assert_called_once()
    assert not c.turns and not c.routed


@pytest.mark.parametrize('text',[
    'Ne consulte pas internet pour le tarif du Louvre.',
    'Quel tarif figurait dans mes notes privees ?',
    'Exemple : "Quel est le tarif du Louvre ?"',
    'Quand je te le demanderai, verifie le tarif du Louvre.',
])
def test_routed_discuss_decision_never_calls_reader(text):
    c=routed_controller('discuss')
    assert c.handle(text,'text',routed=True)['status']=='cancelled'
    c.session.ask.assert_called_once()
    c.reader.assert_not_called()
    assert not c.routed


@pytest.mark.parametrize('source',['twitch','discord','page'])
def test_routed_external_request_is_rejected(source):
    c=routed_controller()
    with pytest.raises(ValueError):c.handle('Quel tarif ? ',source,routed=True)
    c.session.ask.assert_not_called();c.reader.assert_not_called()


@pytest.mark.parametrize('routed',[1,0,None,'true',[],{}])
def test_routed_flag_must_be_boolean(routed):
    c=routed_controller()
    with pytest.raises(ValueError):c.handle('Quel tarif ?', 'text',routed=routed)
    c.session.ask.assert_not_called();c.reader.assert_not_called()


def test_routed_clarification_preserves_provenance_and_exact_followup():
    c=routed_controller('clarify')
    assert c.handle('Quel est le tarif du musee ?', 'text',routed=True)['status']=='clarify'
    assert c.routed and c.can_handle('La question est tarif du Louvre')
    c.session.ask.return_value=('{"decision":"execute"}',0,0)
    assert c.handle('La question est tarif du Louvre','text')['status']=='found'
    assert c.reader.call_args.args[1]=='tarif du Louvre'
    assert not c.routed


@pytest.mark.parametrize('boundary',['stop','Bonjour'])
def test_routed_followup_cancel_or_unrelated_clears_provenance(boundary):
    c=routed_controller('clarify')
    c.handle('Quel est le tarif du musee ?', 'text',routed=True)
    c.handle(boundary,'text')
    assert not c.turns and not c.routed
    assert c.session.ask.call_count==1
    c.reader.assert_not_called()


def test_expired_routed_request_cannot_resume():
    now=[0]
    c=routed_controller('clarify',clock=lambda:now[0])
    c.handle('Quel est le tarif du musee ?', 'text',routed=True)
    now[0]=300
    c.handle('La question est tarif du Louvre','text')
    assert not c.turns and not c.routed
    assert c.session.ask.call_count==1
    c.reader.assert_not_called()


def test_direct_request_replaces_routed_provenance():
    c=routed_controller('clarify')
    c.handle('Quel est le tarif du musee ?', 'text',routed=True)
    c.session.ask.return_value=('{"decision":"execute"}',0,0)
    assert c.handle(TEXT,'text')['status']=='found'
    assert c.reader.call_args.args[1]=='horaires du Louvre'
    assert not c.routed
