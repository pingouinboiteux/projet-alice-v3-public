"""Subject preparation may not weaken proof boundaries or become a stored fact."""
import copy,json
from types import SimpleNamespace
from unittest.mock import Mock
from episode_protocol import dialogue_subject_contract
from v5_context_memory import CarefulMemoryReader

def test_subject_preparation_preserves_source_enum_and_the_callers_contract():
    schema={'type':'object','properties':{'reply':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string','enum':['validation_proof']}}},'required':['reply','evidence_ids'],'additionalProperties':False}
    before=copy.deepcopy(schema);result=dialogue_subject_contract(schema)
    assert schema==before
    assert result['properties']['evidence_ids']==before['properties']['evidence_ids']
    assert not result['additionalProperties']
    assert list(result['properties'])[0]=='phenomenon'
    result['properties']['evidence_ids']['items']['enum'].append('validation_other')
    assert schema==before

def reader(value):
    store=SimpleNamespace(retrieve=lambda *a,**k:[],version=lambda:1)
    session=SimpleNamespace(ask=Mock(return_value=(json.dumps(value),0,{})),count_tokens=lambda _:1)
    return CarefulMemoryReader(session,store,'general_discussion'),session

def test_generated_subject_is_discarded_and_cannot_become_reply_or_memory_metadata():
    instance,session=reader({'phenomenon':'Un sujet non probant','reply':'Texte prononce','evidence_ids':[]})
    result=instance.answer('Lance un sujet',system='validation_persona')
    assert result['reply']=='Texte prononce' and 'phenomenon' not in result
    assert result['sources']==[] and result['admitted_ids']==[]
    assert 'phenomenon' in session.ask.call_args.kwargs['response_schema']['required']

def test_non_dialogue_custom_schema_remains_untouched_even_with_a_similarly_named_field():
    instance,session=reader({'phenomenon':'Valeur du contrat appelant','reply':'Texte','evidence_ids':[]})
    schema={'type':'object','properties':{'reply':{'type':'string'},'phenomenon':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}}},'required':['reply','phenomenon','evidence_ids'],'additionalProperties':False}
    before=copy.deepcopy(schema)
    result=instance.answer('Demande',response_schema=schema)
    assert result['phenomenon']=='Valeur du contrat appelant'
    passed=session.ask.call_args.kwargs['response_schema']
    assert passed['properties']['phenomenon']==schema['properties']['phenomenon']
    assert list(passed['properties'])[0]=='reply' and passed['required']==schema['required']
    assert schema==before
