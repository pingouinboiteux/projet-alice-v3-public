"""Verify inference settings and routing without loading a model or real memory."""
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from chat import Session
from episodic_memory import Reader
from v5_context_memory import CarefulMemoryReader
from v5_context_memory import V5Reader

def session_stub(token_count=5):
    session=Session.__new__(Session);session.inference_lock=threading.RLock()
    session.model_spec={'family':'gemma4','expose_schema':True}
    requests=[]
    def request(path,body=None):
        requests.append((path,body))
        if path=='/apply-template':return {'prompt':'synthetic'}
        if path=='/tokenize':return {'tokens':[1]*token_count}
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"ok","evidence_ids":[]}'}}],'usage':{}}
    session.request=request
    return session,requests

def test_memory_reply_uses_matching_gemma_template_and_output_limit():
    session,requests=session_stub()
    session.ask_memory([{'role':'user','content':'Question fictive'}],{'type':'object'})
    template=next(b for p,b in requests if p=='/apply-template')
    completion=next(b for p,b in requests if p=='/v1/chat/completions')
    assert template['chat_template_kwargs']==completion['chat_template_kwargs']=={'enable_thinking':False}
    assert 'reasoning_effort' not in completion
    assert completion['max_tokens']==2048 and completion['temperature']==0

def test_regular_and_background_calls_keep_the_same_native_mode():
    session,requests=session_stub();messages=[{'role':'user','content':'Question'}]
    session.ask_memory(messages);session.ask(messages);session.ask_background(messages,{'type':'object'})
    payloads=[b for p,b in requests if p=='/v1/chat/completions']
    assert all('reasoning_effort' not in p and p['chat_template_kwargs']=={'enable_thinking':False} for p in payloads)
    assert [p['max_tokens'] for p in payloads]==[2048,2048,256]

def test_oversized_memory_input_is_rejected_before_generation():
    session,requests=session_stub(5501)
    with pytest.raises(RuntimeError):session.ask_memory([{'role':'user','content':'Question'}])
    assert not any(p=='/v1/chat/completions' for p,b in requests)

@pytest.mark.parametrize('kind,has_sources,expected',[
    ('specific_fact',True,1),('specific_fact',False,0),('general_discussion',True,0)])
def test_only_personal_recall_with_evidence_uses_medium(kind,has_sources,expected):
    sources=[{'id':'validation_source','date':'2026-01-01','messages':[{'role':'user','content':'texte fictif'}]}] if has_sources else []
    store=SimpleNamespace(retrieve=lambda *a,**kw:sources.copy(),version=lambda:1)
    answer=(' {"reply":"Texte","evidence_ids":[]} ',0,{})
    session=SimpleNamespace(ask=Mock(return_value=answer),ask_memory=Mock(return_value=answer),count_tokens=lambda m:1,count_memory_tokens=lambda m:2)
    CarefulMemoryReader(session,store,query_kind=kind).answer('Question')
    assert session.ask_memory.call_count==expected
    assert session.ask.call_count==1-expected

def test_old_reader_keeps_low_reasoning():
    store=SimpleNamespace(retrieve=lambda *a,**kw:[{'id':'validation_source','date':'2026-01-01','messages':[{'role':'user','content':'texte'}]}],version=lambda:1)
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"Texte","evidence_ids":[]}',0,{})),ask_memory=Mock(),count_tokens=lambda m:1)
    Reader(session,store,query_kind='specific_fact').answer('Question')
    session.ask_memory.assert_not_called()

def test_medium_budget_removes_whole_sources_without_changing_archive():
    sources=[{'id':'validation_'+str(i),'date':'2026-01-01','messages':[{'role':'user','content':'complete synthetic source '+str(i)}]} for i in range(2)]
    store=SimpleNamespace(retrieve=lambda *a,**kw:sources.copy(),version=lambda:1)
    def count_memory(messages):
        payload=messages[1]['content'].split(' : ',1)[1]
        return 5501 if len(json.loads(payload)['archives'])>1 else 10
    session=SimpleNamespace(ask=Mock(),ask_memory=Mock(return_value=('{"reply":"Texte","evidence_ids":[]}',0,{})),count_tokens=lambda m:1,count_memory_tokens=count_memory)
    result=CarefulMemoryReader(session,store,query_kind='specific_fact').answer('Question')
    assert result['budget_omitted_sources']==1 and len(result['sources'])==1
    assert len(sources)==2 and result['sources'][0]['messages']==sources[0]['messages']

def test_rejected_general_preference_does_not_use_medium():
    sources=[{'id':'validation_source','date':'2026-01-01','messages':[{'role':'user','content':'occasion unique'}]}]
    store=SimpleNamespace(retrieve=lambda *a,**kw:sources.copy(),version=lambda:1)
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"Inconnu","evidence_ids":[]}',0,{})),ask_memory=Mock(),count_tokens=lambda m:1,count_memory_tokens=lambda m:1)
    with patch('episode_protocol._personal',return_value=([],{'requires_general_preference':True})):
        CarefulMemoryReader(session,store,query_kind='general_preference').answer('Question')
    session.ask_memory.assert_not_called()

def test_fact_reader_separates_style_states_and_intention_from_evidence():
    sources=[{'id':'validation_source','date':'2026-01-01','messages':[{'role':'user','content':'Le rendez-vous est vendredi.'}]}]
    store=SimpleNamespace(retrieve=lambda *a,**kw:sources.copy(),version=lambda:1)
    session=SimpleNamespace(ask=Mock(),ask_memory=Mock(return_value=('{"reply":"Vendredi","evidence_ids":["validation_source"]}',0,{})),count_tokens=lambda m:1,count_memory_tokens=lambda m:1)
    schema={'type':'object','properties':{'reply':{'type':'string'},'evidence_ids':{'type':'array'},'reflection':{'type':'string','enum':['repondre']}},'required':['reply','evidence_ids','reflection']}
    result=CarefulMemoryReader(session,store,query_kind='specific_fact').answer('Quand ?',system='STYLE_PRIVATE',auxiliary={'indication_de_ton':'MOOD_PRIVATE'},response_schema=schema)
    messages=session.ask_memory.call_args.args[0]
    assert 'STYLE_PRIVATE' not in json.dumps(messages) and 'MOOD_PRIVATE' not in json.dumps(messages)
    assert 'Le rendez-vous est vendredi.' in json.dumps(messages,ensure_ascii=False)
    assert 'reflection' not in session.ask_memory.call_args.kwargs['response_schema']['properties']
    assert result['reflection']=='repondre'

def test_general_conversation_retains_personality_and_emotions():
    store=SimpleNamespace(retrieve=lambda *a,**kw:[],version=lambda:1)
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"Discutons","evidence_ids":[]}',0,{})),ask_memory=Mock(),count_tokens=lambda m:1)
    CarefulMemoryReader(session,store,query_kind='general_discussion').answer('Discutons',system='STYLE_PRIVATE',auxiliary={'indication_de_ton':'MOOD_PRIVATE'})
    messages=json.dumps(session.ask.call_args.args[0])
    assert 'STYLE_PRIVATE' in messages and 'MOOD_PRIVATE' in messages
    session.ask_memory.assert_not_called()

def test_reranker_cannot_veto_both_best_retrieval_sources():
    sources=[{'id':'validation_'+str(i),'date':'2026-01-01','messages':[{'role':'user','content':'partial information '+str(i)}],'search_excerpt':'partial information'} for i in range(3)]
    database=Mock();database.execute.return_value.fetchone.return_value=(1,)
    database.execute.return_value.__iter__=lambda s:iter([])
    store=SimpleNamespace(db=database,candidates=lambda *a,**kw:sources.copy(),version=lambda:1)
    captured=[]
    def answer(reader,*args,**kwargs):
        captured.extend(reader.episodes.retrieve('question'))
        return {'reply':'test','sources':captured}
    with patch('reviewed_memory_reader.ask',return_value={'kind':'specific_fact','ids':[]}),patch.object(CarefulMemoryReader,'answer',answer):
        V5Reader(SimpleNamespace(),store).answer('question')
    assert [s['id'] for s in captured]==['validation_0','validation_1']
