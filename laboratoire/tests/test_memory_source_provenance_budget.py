"""Provenance batching preserves whole sources and local reference boundaries."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memory_source_provenance import PROVENANCE, resolve


def sources():
    return [{'id':f'validation_source_{i}','date':'2026-01-01','messages':[
        {'role':'assistant','content':f'Proposition complete {i}.'},
        {'role':'user','content':f'Oui, confirmation complete {i}.'}]} for i in range(3)]


def fake_session(max_sources, *, invalid=None, object_kind='fait_personnel'):
    measured=[]
    def count(messages,schema):
        payload=json.loads(messages[1]['content'])
        records=payload['messages']
        measured.append((copy.deepcopy(messages),copy.deepcopy(schema)))
        # Simulate schema-inclusive accounting: bound references are indispensable.
        assert 'confirmations' in schema['properties']
        if records and len({r['echange'] for r in records})>max_sources:return 5501
        return 4000
    def ask(messages,response_schema=None):
        records=json.loads(messages[1]['content'])['messages']
        assert len({r['echange'] for r in records})<=max_sources
        pairs=[{'assistant':r['id'],'user':next(u['id'] for u in records
            if u['echange']==r['echange'] and u['role']=='user')}
            for r in records if r['role']=='assistant']
        if invalid=='cross_batch':pairs=[{'assistant':'e0_m0','user':'e0_m1'}]
        if invalid=='cross_source' and pairs:pairs[0]['user']='e1_m1'
        objet=object_kind
        if invalid=='object_change' and response_schema['properties']['objet']['enum']==['fait_personnel']:
            objet='paroles_assistant'
        return json.dumps({'objet':objet,'confirmations':pairs}),0,{}
    session=SimpleNamespace(ask=Mock(side_effect=ask),count_response_tokens=Mock(side_effect=count))
    return session,measured


def test_short_input_keeps_the_original_single_call_prompt_and_reference_schema():
    archives=sources();session,measured=fake_session(3)
    view,meta=resolve(session,archives,'Quelle proposition ?')
    assert view==archives and meta['confirmed_contexts']==3
    assert 'rejected_confirmations' not in meta
    session.ask.assert_called_once()
    messages=session.ask.call_args.args[0];schema=session.ask.call_args.kwargs['response_schema']
    assert messages[0]=={'role':'system','content':PROVENANCE}
    assert schema['properties']['objet']['enum']==['fait_personnel','paroles_assistant']
    assert schema['properties']['confirmations']['items']['properties']['assistant']['enum']==['e0_m0','e1_m0','e2_m0']
    assert measured==[(messages,schema)]


def test_combined_oversize_is_split_without_losing_source_text_or_global_ids():
    archives=sources();before=copy.deepcopy(archives);session,measured=fake_session(1)
    view,meta=resolve(session,archives,'Quelle proposition ?')
    assert view==before and archives==before
    assert meta['confirmed_contexts']==3 and meta['source_batches']==3
    assert session.ask.call_count==3
    received=[]
    for index,call in enumerate(session.ask.call_args_list):
        messages=call.args[0];schema=call.kwargs['response_schema']
        payload=json.loads(messages[1]['content']);received.extend(payload['messages'])
        assert payload['question']=='Quelle proposition ?'
        assert len({r['echange'] for r in payload['messages']})==1
        assert schema['properties']['objet']['enum']==(['fait_personnel','paroles_assistant'] if index==0 else ['fait_personnel'])
        assert any(previous==messages for previous,_ in measured)
    assert [r['content'] for r in received]==[m['content'] for source in archives for m in source['messages']]
    assert [r['id'] for r in received]==['e0_m0','e0_m1','e1_m0','e1_m1','e2_m0','e2_m1']


def test_oversized_individual_source_refuses_before_any_generation():
    archives=sources();before=copy.deepcopy(archives);session,_=fake_session(1)
    def count(messages,schema):
        records=json.loads(messages[1]['content'])['messages']
        return 5501 if any(r['echange']==2 for r in records) or len(records)>2 else 4000
    session.count_response_tokens.side_effect=count
    with pytest.raises(ValueError,match='Provenance source exceeds'):
        resolve(session,archives,'Quelle proposition ?')
    session.ask.assert_not_called()
    assert archives==before


@pytest.mark.parametrize('invalid,max_sources',[('cross_batch',1),('cross_source',2)])
def test_invalid_local_references_are_omitted_without_admitting_assistant_context(invalid,max_sources):
    archives=sources();before=copy.deepcopy(archives)
    session,_=fake_session(max_sources,invalid=invalid)
    view,meta=resolve(session,archives,'Quelle proposition ?')
    assert archives==before
    assert meta['rejected_confirmations']==2 and meta['confirmed_contexts']==1
    assert meta['hidden_assistant_turns']==2
    assert [message for source in view for message in source['messages'] if message['role']=='user']==[
        message for source in before for message in source['messages'] if message['role']=='user']
    assert sum(message['role']=='assistant' for source in view for message in source['messages'])==1


def test_reclassified_object_still_fails_closed():
    archives=sources();before=copy.deepcopy(archives)
    session,_=fake_session(1,invalid='object_change')
    with pytest.raises(ValueError,match='Inconsistent source question object'):
        resolve(session,archives,'Quelle proposition ?')
    assert archives==before


def test_schema_tokens_can_force_splitting_even_when_message_text_fits():
    archives=sources();session,_=fake_session(1)
    session.count_tokens=Mock(return_value=1)
    def count(messages,schema):
        enum=schema['properties']['confirmations']['items']['properties']['assistant']['enum']
        return 5501 if len(enum)>1 else 5500
    session.count_response_tokens.side_effect=count
    view,_=resolve(session,archives,'Quelle proposition ?')
    assert view==archives and session.ask.call_count==3
    session.count_tokens.assert_not_called()


def test_assistant_words_object_stays_consistent_across_all_batches():
    archives=sources();session,_=fake_session(1,object_kind='paroles_assistant')
    view,meta=resolve(session,archives,'Qu avais-tu propose ?')
    assert view==archives and meta['object']=='paroles_assistant'
    assert all(call.kwargs['response_schema']['properties']['objet']['enum']==['paroles_assistant']
               for call in session.ask.call_args_list[1:])


@pytest.mark.parametrize('plan',[
    [], {'objet':'fait_personnel'},
    {'objet':[],'confirmations':[]},
    {'objet':'fait_personnel','confirmations':{}},
    {'objet':'fait_personnel','confirmations':[{'assistant':'e0_m0'}]},
    {'objet':'fait_personnel','confirmations':[{'assistant':1,'user':'e0_m1'}]},
    {'objet':'fait_personnel','confirmations':[{'assistant':'e0_m0','user':'e0_m1'}]*9}])
def test_malformed_plans_and_pair_types_are_still_blocked(plan):
    archives=sources();before=copy.deepcopy(archives);session,_=fake_session(3)
    session.ask.side_effect=None
    session.ask.return_value=(json.dumps(plan),0,{})
    with pytest.raises(ValueError):resolve(session,archives,'Quelle proposition ?')
    assert archives==before


def test_valid_confirmation_survives_beside_rejected_unknown_and_backward_pairs():
    archives=sources();archives[0]['messages'].append({'role':'assistant','content':'Hypothese jamais confirmee.'})
    before=copy.deepcopy(archives);session,_=fake_session(3)
    session.ask.side_effect=None
    session.ask.return_value=(json.dumps({'objet':'fait_personnel','confirmations':[
        {'assistant':'e0_m0','user':'e0_m1'},
        {'assistant':'missing','user':'e0_m1'},
        {'assistant':'e0_m2','user':'e0_m1'}]}),0,{})
    view,meta=resolve(session,archives,'Quelle proposition ?')
    assert archives==before and view[0]['messages']==before[0]['messages'][:2]
    assert meta['rejected_confirmations']==2 and meta['confirmed_contexts']==1
    assert all(message['role']=='user' for source in view[1:] for message in source['messages'])
