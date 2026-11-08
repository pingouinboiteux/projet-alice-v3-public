import json
from unittest.mock import Mock
import pytest
from search_request import can_handle_search, is_search_followup, interpret_search
from intent_router import route

TEXT='Cherche sur internet les horaires du Louvre'
QUESTION='les horaires du Louvre'

def session(decision='execute'):
    s=Mock()
    s.ask.return_value=(json.dumps({'decision':decision}),0,0)
    return s

@pytest.mark.parametrize('text',[TEXT,'Cherche sur le web les horaires du Louvre','Cherche les horaires du musée du Louvre','/rechercher météo Paris','Peux-tu chercher les horaires du Louvre ?'])
def test_candidate(text):assert can_handle_search(text)

@pytest.mark.parametrize('text',['Cherche mes notes','Cherche dans ma mémoire','Cherche mes souvenirs','Cherche https://example.org prix','Trouve le prix sur ce site','Suis le lien Tarifs','Ne cherche pas sur internet','Par exemple cherche le Louvre','"Cherche le Louvre"',None])
def test_other_requests(text):assert not can_handle_search(text)

@pytest.mark.parametrize('text',['oui','Paris','Bonjour','"stop"'])
def test_no_unlabelled_followup(text):assert not is_search_followup(text)

def test_exact_query():
    result=interpret_search(session(),[TEXT],'text')
    assert result['target']=={'question':QUESTION}

def test_model_cannot_invent_query():
    s=session()
    s.ask.return_value=(' {"decision":"execute","question":"invented"}',0,0)
    assert interpret_search(s,[TEXT],'voice')['status']=='clarify'
    assert s.ask.call_count==1


def test_correction_replaces_old_question():
    turns=[TEXT,'La recherche est les horaires du musee de Dijon']
    result=interpret_search(session(),turns,'text')
    assert result['target']['question']=='les horaires du musee de Dijon'
    ref=result['sources']['question']
    assert ref['turn']==1
    assert turns[1][ref['start']:ref['end']]==result['target']['question']

@pytest.mark.parametrize('source',['page','twitch','discord',None])
def test_local_only(source):
    s=Mock();assert interpret_search(s,[TEXT],source)['status']=='clarify';s.ask.assert_not_called()

@pytest.mark.parametrize('tail',[' si je finis ma partie',' demain quand je te le dirai',' mais ne lance rien'])
def test_gate_checks_entire_original(tail):
    s=session(decision='discuss')
    assert interpret_search(s,[TEXT+tail],'text')['status']=='discuss'
    assert TEXT+tail in s.ask.call_args.args[0][1]['content']

@pytest.mark.parametrize('text',['/rechercher météo','/rechercher meilleur casque','Cherche les horaires du musée'])
def test_ambiguity_does_not_execute(text):
    s=Mock();s.ask.return_value=('{"decision":"clarify"}',0,0)
    assert interpret_search(s,[text],'text')['status']=='clarify'

def test_question_limit():
    q='a'*501
    assert interpret_search(session(),['/rechercher '+q],'text')['status']=='clarify'

def test_router_keeps_original():
    s=Mock();s.ask.return_value=('{"kind":"web_search","value":"invented","reply":"Recherche"}',0,0)
    action,_=route(s,[{'role':'system','content':'Test'}],TEXT)
    assert action.kind=='web_search' and action.value==TEXT
def test_explicit_existing_search_service_keeps_its_dedicated_route():
    from search_request import can_handle_search
    for text in ('Cherche sur Wikipedia volcan', 'Cherche sur Google les horaires du Louvre'):
        assert not can_handle_search(text)



@pytest.mark.parametrize('text,question',[
    ('Alice, cherche sur internet la date de fondation de Carthage.', 'la date de fondation de Carthage.'),
    ('Recherche sur le web les horaires du musee Azur a Lille.', 'les horaires du musee Azur a Lille.'),
    ('Cherche un casque filaire pour jouer sur PC, moins de 90 euros.', 'un casque filaire pour jouer sur PC, moins de 90 euros.'),
    ('Peux-tu chercher "Ne cherche pas" au cinema ?', '"Ne cherche pas" au cinema ?'),
    ('  /rechercher  nom nom  ', 'nom nom'),
    ('/rechercher La question est quelle heure ?', 'La question est quelle heure ?'),
])
def test_exact_extraction_single_decision(text,question):
    s=session()
    result=interpret_search(s,[text],'text')
    assert result['target']['question']==question
    ref=result['sources']['question']
    assert text[ref['start']:ref['end']]==question
    assert s.ask.call_count==1
    payload=json.loads(s.ask.call_args.args[0][1]['content'])
    assert payload=={'tours_locaux':[text],'question':question}


@pytest.mark.parametrize('text',['/rechercher', '/rechercher '+ 'a'*501])
def test_invalid_question_never_calls_model(text):
    s=session()
    assert interpret_search(s,[text],'text')['status']=='clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('raw',['{}','{"decision":"cancel"}','{"decision":true}',
    '{"decision":"execute","reason":"ok"}','not json'])
def test_invalid_decision_never_executes(raw):
    s=session();s.ask.return_value=(raw,0,0)
    assert interpret_search(s,[TEXT],'text')['status']=='clarify'


def test_unrelated_followup_never_calls_model():
    s=session()
    assert interpret_search(s,[TEXT,'Bonjour'],'text')['status']=='clarify'
    s.ask.assert_not_called()


def test_cancel_never_calls_model():
    s=session()
    assert interpret_search(s,[TEXT,'stop'],'text')=={'status':'cancel'}
    s.ask.assert_not_called()


def test_same_question_repeated_has_exact_latest_offsets():
    result=interpret_search(session(),[TEXT,'La question est '+QUESTION],'text')
    assert result['status']=='ready' and result['sources']['question']['turn']==1


def test_accented_correction_keeps_original_unicode_offsets():
    correction='Plut\u00f4t, la question est cr\u00e9ation du th\u00e9\u00e2tre'
    result=interpret_search(session(),[TEXT,correction],'text')
    ref=result['sources']['question']
    assert correction[ref['start']:ref['end']]=='cr\u00e9ation du th\u00e9\u00e2tre'


def test_explicit_command_web_prefix_is_removed():
    result=interpret_search(session(),['/rechercher sur internet date de fondation'],'text')
    assert result['target']['question']=='date de fondation'


def test_routed_question_is_whole_original_with_exact_offsets():
    text='  Quel est le tarif du musee Azur a Lille ?  '
    s=session()
    result=interpret_search(s,[text],'text',routed=True)
    assert result['target']['question']==text
    assert result['sources']['question']=={'turn':0,'start':0,'end':len(text)}
    assert json.loads(s.ask.call_args.args[0][1]['content'])['question']==text


@pytest.mark.parametrize('routed',[1,0,None,'true',[],{}])
def test_invalid_routed_provenance_never_calls_model(routed):
    s=session()
    assert interpret_search(s,['Quel tarif ?'],'text',routed=routed)['status']=='clarify'
    s.ask.assert_not_called()


@pytest.mark.parametrize('source',['twitch','discord','page',None])
def test_routed_never_grants_external_access(source):
    s=session()
    assert interpret_search(s,['Quel tarif ?'],source,routed=True)['status']=='clarify'
    s.ask.assert_not_called()


def test_routed_question_still_obeys_size_limit():
    s=session()
    assert interpret_search(s,['a'*501],'text',routed=True)['status']=='clarify'
    s.ask.assert_not_called()
