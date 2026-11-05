"""Source boundaries must hold independently of generated wording."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from memory_source_provenance import resolve
from v5_context_memory import CarefulMemoryReader

def archive(messages,identity='validation_source'):
    return {'id':identity,'date':'2026-01-01','messages':[{'role':role,'content':text} for role,text in messages]}

def session(plan):return SimpleNamespace(ask=Mock(return_value=(json.dumps(plan),0,{})))

def test_user_only_sources_need_no_extra_model_call_and_remain_intact():
    sources=[archive([('user','Le carnet est bleu.')])];fake=session({})
    view,meta=resolve(fake,sources,'Quelle couleur ?')
    assert view==sources and view is not sources and not meta['called']
    fake.ask.assert_not_called()

def test_unconfirmed_assistant_value_is_not_in_the_factual_read_view():
    sources=[archive([('user','Prix inconnu.'),('assistant','Peut-etre 71 euros.'),('user','Non verifie.')])]
    before=copy.deepcopy(sources)
    view,meta=resolve(session({'objet':'fait_personnel','confirmations':[]}),sources,'Quel prix ?')
    assert '71' not in json.dumps(view) and sources==before and meta['hidden_assistant_turns']==1
    assert [m['content'] for m in view[0]['messages']]==['Prix inconnu.','Non verifie.']

def test_contextual_yes_keeps_the_confirmed_assistant_question():
    sources=[archive([('assistant','Ton train est a 17h35 ?'),('user','Oui.')])]
    view,meta=resolve(session({'objet':'fait_personnel','confirmations':[{'assistant':'e0_m0','user':'e0_m1'}]}),sources,'Quelle heure ?')
    assert view==sources and meta['confirmed_contexts']==1

def test_question_about_assistant_words_keeps_the_proposal_without_confirmation():
    sources=[archive([('user','Je ne sais pas.'),('assistant','Peut-etre 71 euros.')])]
    view,meta=resolve(session({'objet':'paroles_assistant','confirmations':[]}),sources,'Qu avais-tu propose ?')
    assert view==sources and meta['hidden_assistant_turns']==0

@pytest.mark.parametrize('pair',[
 {'assistant':'missing','user':'e0_m1'},
 {'assistant':'e0_m0','user':'e1_m0'},
 {'assistant':'e0_m2','user':'e0_m1'},
 {'assistant':'e0_m1','user':'e0_m0'}])
def test_invalid_confirmation_links_are_rejected_without_changing_the_source(pair):
    sources=[archive([('assistant','Proposition.'),('user','Oui.'),('assistant','Autre proposition.')]),archive([('user','Oui.')],'validation_other')]
    before=copy.deepcopy(sources)
    view,meta=resolve(session({'objet':'fait_personnel','confirmations':[pair]}),sources,'Question')
    assert sources==before
    assert meta['rejected_confirmations']==1 and meta['confirmed_contexts']==0
    assert meta['hidden_assistant_turns']==2
    assert all(message['role']=='user' for source in view for message in source['messages'])
    assert [message for source in view for message in source['messages']]==[
        message for source in sources for message in source['messages'] if message['role']=='user']

def test_preference_context_is_preserved_without_becoming_admissible_evidence():
    source=archive([('user','Uniquement pour cette nuit, des reponses breves.')])
    store=SimpleNamespace(retrieve=lambda *a,**k:[source],version=lambda:1)
    fake=SimpleNamespace(ask=Mock(return_value=('{"reply":"Habitude inconnue","evidence_ids":[]}',0,{})),count_tokens=lambda _:1)
    with patch('episode_protocol._personal',return_value=([],{'requires_general_preference':True})):
        result=CarefulMemoryReader(fake,store,'general_preference').answer('Toujours bref ?',system='PERSONA_TO_KEEP_OUT',auxiliary={'humeur':'temporaire'})
    messages=fake.ask.call_args.args[0];payload=json.loads(messages[1]['content'].split(' : ',1)[1])
    assert payload['archives']==[] and payload['contexte_non_probant'][0]['messages']==source['messages']
    assert payload['etat_lecture']=={'sources_selectionnees':1,'sources_admises':0}
    assert 'PERSONA_TO_KEEP_OUT' not in messages[0]['content']
    assert result['admitted_ids']==[] and fake.ask.call_args.kwargs['response_schema']['properties']['evidence_ids']['maxItems']==0

def test_recent_history_cannot_reintroduce_the_masked_assistant_suggestion():
    messages=[('user','Prix inconnu.'),('assistant','Peut-etre 71 euros.'),('user','Non verifie.')]
    source=archive(messages);store=SimpleNamespace(retrieve=lambda *a,**k:[source],version=lambda:1)
    def ask(messages,response_schema=None):
        if 'confirmations' in response_schema['properties']:return '{"objet":"fait_personnel","confirmations":[]}',0,{}
        return '{"reply":"Prix inconnu","evidence_ids":[]}',0,{}
    fake=SimpleNamespace(ask=Mock(side_effect=ask),count_tokens=lambda _:1)
    CarefulMemoryReader(fake,store,'specific_fact').answer('Quel prix ?',history=source['messages'])
    final=fake.ask.call_args.args[0]
    assert '71' not in json.dumps(final) and '71' in json.dumps(source)

def test_rejected_evidence_cannot_erase_the_outer_preference_question_kind():
    source=archive([('user','Pour ce tournoi seulement, je veux du silence.')])
    store=SimpleNamespace(retrieve=lambda *a,**k:[source],version=lambda:1)
    fake=SimpleNamespace(ask=Mock(return_value=('{"reply":"Habitude inconnue","evidence_ids":[]}',0,{})),count_tokens=lambda _:1)
    with patch('episode_protocol._personal',return_value=([],{'requires_general_preference':False})):
        result=CarefulMemoryReader(fake,store,'general_preference').answer('Toujours silencieux ?',system='PERSONA')
    messages=fake.ask.call_args.args[0]
    assert 'PERSONA' not in messages[0]['content']
    payload=json.loads(messages[1]['content'].split(' : ',1)[1])
    assert payload['archives']==[] and payload['contexte_non_probant'][0]['messages']==source['messages']
    assert result['admitted_ids']==[]

def test_budget_can_omit_context_without_claiming_no_sources_were_consulted():
    source=archive([('user','Pour cette nuit seulement, une reponse courte.')])
    store=SimpleNamespace(retrieve=lambda *a,**k:[source],version=lambda:1)
    def precise(messages,schema):
        payload=json.loads(messages[1]['content'].split(' : ',1)[1])
        return 5501 if payload.get('contexte_non_probant') else 10
    fake=SimpleNamespace(ask=Mock(return_value=('{"reply":"Habitude inconnue","evidence_ids":[]}',0,{})),count_tokens=lambda _:1,count_response_tokens=precise)
    with patch('episode_protocol._personal',return_value=([],{'requires_general_preference':True})):
        CarefulMemoryReader(fake,store,'general_preference').answer('Toujours bref ?')
    payload=json.loads(fake.ask.call_args.args[0][1]['content'].split(' : ',1)[1])
    assert payload['contexte_non_probant']==[]
    assert payload['etat_lecture']=={'sources_selectionnees':1,'sources_admises':0,'contextes_omis_pour_budget':1}
    assert source['messages'][0]['content']=='Pour cette nuit seulement, une reponse courte.'
