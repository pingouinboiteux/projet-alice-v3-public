"""Temporary thoughts cannot repeatedly steer later private turns."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from background_thoughts import Thoughts
from episode_conversation import Conversation
from test_episodic_memory import Search

def fixture():
    now=[0]
    session=SimpleNamespace(ask_background=Mock(return_value=('{"idea":"SYNTHETIC_THOUGHT"}',0,{})))
    thoughts=Thoughts(session,delay=1,cooldown=300,clock=lambda:now[0])
    history=[{'role':'user','content':'Ancien sujet'},{'role':'assistant','content':'Ancienne reponse'}]
    thoughts.idle(history);now[0]=2;thoughts.tick()
    assert thoughts.context()=='SYNTHETIC_THOUGHT'
    return thoughts,session,now,history

def test_idea_survives_resumption_but_not_a_completed_new_exchange():
    thoughts,session,now,history=fixture()
    thoughts.active();assert thoughts.context()=='SYNTHETIC_THOUGHT'
    thoughts.idle(history+[{'role':'user','content':'Nouveau sujet'},{'role':'assistant','content':'Nouvelle reponse'}])
    assert thoughts.context()==''
    now[0]=5;thoughts.tick();session.ask_background.assert_called_once()

def test_same_private_history_during_public_activity_does_not_consume_idea():
    thoughts,_,_,history=fixture()
    thoughts.active();thoughts.idle([dict(m) for m in history])
    assert thoughts.context()=='SYNTHETIC_THOUGHT'

def test_change_after_700th_character_invalidates_full_context_identity():
    thoughts,_,_,_=fixture()
    history=[{'role':'user','content':'A'*700+' old'}]
    thoughts.idle(history);thoughts.idea='OLD';thoughts.expires=100
    thoughts.idle([{'role':'user','content':'A'*700+' new'}])
    assert thoughts.context()==''

def test_late_generation_is_discarded_when_history_changes_without_active_call():
    now=[0];session=SimpleNamespace();thoughts=Thoughts(session,delay=1,clock=lambda:now[0])
    def generate(*args):
        thoughts.idle([{'role':'user','content':'New topic'}])
        return '{"idea":"STALE"}',0,{}
    session.ask_background=generate
    thoughts.idle([{'role':'user','content':'Old topic'}]);now[0]=2;thoughts.tick()
    assert thoughts.context()==''

def test_new_idea_can_still_be_generated_after_cooldown():
    thoughts,session,now,history=fixture()
    thoughts.idle(history+[{'role':'user','content':'New topic'}]);now[0]=303;thoughts.tick()
    assert thoughts.context()=='SYNTHETIC_THOUGHT' and session.ask_background.call_count==2
    thoughts.clear();assert thoughts.context()=='' and thoughts.history_key is None

def test_actual_conversation_gets_same_thought_only_on_first_new_turn(tmp_path):
    thoughts,session,now,history=fixture();session.thoughts=thoughts
    memory=Conversation(session,'validation_thought_lifetime',tmp_path/'validation_memory.db',Search())
    memory.ask_json=lambda *a,**k:{'feeling':''}
    try:
        auxiliary=[]
        for text in ['Nouveau sujet','Continuons ici','Encore une autre idee']:
            thoughts.active()
            with patch('episode_conversation.Reader.answer',return_value={'reply':'Reponse fictive','reflection':'repondre','evidence_ids':[]}) as reader:
                memory.answer(text,history,'system',lambda _:False)
            auxiliary.append(reader.call_args.args[3])
            history=history+[{'role':'user','content':text},{'role':'assistant','content':'Reponse fictive'}]
            thoughts.idle(history)
        assert [bool(a.get('idee_silencieuse_non_factuelle')) for a in auxiliary]==[True,False,False]
        assert all('SYNTHETIC_THOUGHT' not in repr(memory.episodes.get(row[0])) for row in memory.episodes.db.execute('SELECT id FROM episodes'))
    finally:memory.close();thoughts.close()

def test_one_atomic_thought_snapshot_per_answer(tmp_path):
    thoughts=SimpleNamespace(context=Mock(side_effect=['FIRST_SNAPSHOT','SECOND_SNAPSHOT']),clear=Mock())
    session=SimpleNamespace(thoughts=thoughts)
    memory=Conversation(session,'validation_single_snapshot',tmp_path/'validation_memory.db',Search())
    memory.ask_json=lambda *a,**k:{'feeling':''}
    try:
        with patch('episode_conversation.Reader.answer',return_value={'reply':'Fictif','reflection':'','evidence_ids':[]}) as reader:
            memory.answer('Question fictive',[{'role':'user','content':'Contexte fictif'}],'system',lambda _:False)
        thoughts.context.assert_called_once()
        assert reader.call_args.args[3]['idee_silencieuse_non_factuelle']=='FIRST_SNAPSHOT'
    finally:memory.close()
