"""Repeated input representation must not discard archival evidence or replies."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from episodic_memory import Reader
from dialogue_context_dedup import TURN_CONTINUITY

def turn(role,text):return {'role':role,'content':text}

@pytest.mark.parametrize('full_overlap',[True,False])
def test_duplicate_current_exchange_is_referenced_only_when_history_is_complete(full_overlap):
    messages=[turn('user','Uniquement pour dimanche.'),turn('assistant','Quel choix ?'),turn('user','Le code est SYNTHETIC_CODE.')]
    source={'id':'validation_current','date':'2026-03-02','messages':messages}
    archive=SimpleNamespace(retrieve=lambda *a,**k:[source],version=lambda:1,current_episode_id='validation_current')
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"SYNTHETIC_CODE","evidence_ids":["validation_current"]}',0,{})))
    history=messages if full_overlap else messages[1:]
    with patch.object(Reader,'compact_dialogue',True),patch.object(Reader,'progress_dialogue',True):
        value=Reader(session,archive,query_kind='specific_fact').answer('Quel code ?',history)
    wire=session.ask.call_args.args[0];shown=json.loads(wire[1]['content'].split(' : ',1)[1])['archives'][0]
    assert ('messages' not in shown)==full_overlap
    assert shown['id']==source['id'] and shown['date']==source['date']
    assert source['messages']==messages and value['sources'][0]['messages']==messages
    assert value['reply']=='SYNTHETIC_CODE' and value['evidence_ids']==['validation_current']
    assert wire[2:2+len(history)]==history and wire[-1]['content']=='Quel code ?'
    assert TURN_CONTINUITY in wire[0]['content']
    assert 'Uniquement pour dimanche.' in json.dumps(wire,ensure_ascii=False)

def test_identical_words_in_other_episode_keep_historical_date_and_full_context():
    messages=[turn('user','Demain je pars.'),turn('assistant','D accord.')]
    old={'id':'validation_old','date':'2025-01-01','messages':messages}
    archive=SimpleNamespace(retrieve=lambda *a,**k:[old],version=lambda:1,current_episode_id='validation_current')
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"Reponse","evidence_ids":[]}',0,{})))
    with patch.object(Reader,'compact_dialogue',True):Reader(session,archive,'specific_fact').answer('Quand ?',messages)
    shown=json.loads(session.ask.call_args.args[0][1]['content'].split(' : ',1)[1])['archives'][0]
    assert shown['messages']==messages and shown['date']=='2025-01-01'

def test_control_calls_keep_greedy_sampling_after_experimental_dialogue():
    from test_memory_inference_contract import session_stub
    session,requests=session_stub();messages=[turn('user','synthetic')];schema={'type':'object'}
    session.ask_dialogue(messages,schema);session.ask(messages,schema);session.ask_memory(messages,schema)
    payloads=[body for path,body in requests if path=='/v1/chat/completions']
    assert [p['temperature'] for p in payloads]==[0.7,0,0]
    assert all(p['max_tokens']==2048 and p['response_format']['schema']==schema for p in payloads)
