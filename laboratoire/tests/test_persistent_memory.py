import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from persistent_memory import Store, Memory
from local_mood import MoodEngine


def add(store,text,key,request='validation_source_0001'):
    event,_=store.record_event(request_id=request,role='user',channel='text',content=text)
    fact=store.remember(statement=text,kind='confirmed',confidence=1,event_id=event.id,evidence_quote=text,key=key)
    return fact,event


def test_correction_sources_fts_reopen_and_complete_forget(tmp_path):
    path=tmp_path/'validation_memory.sqlite3'
    with Store('validation_person',path) as store:
        old,e=add(store,'Je vis a Lyon.','user.residence')
        new,_=add(store,'Je vis a Lille.','user.residence','validation_source_0002')
        add(store,'Mon chat est Tango.','user.pet','validation_source_0003')
        store._connection.execute('INSERT INTO vectors VALUES(?,?)',(new.id,b'fictional_vector'))
        store._connection.execute('INSERT INTO reflections VALUES(?,?,?,?)',('validation_note',e.id,'Penser a Lyon',time.time()+100))
        assert [r['statement'] for r in store.rows() if r['memory_key']=='user.residence']==['Je vis a Lille.']
        assert not store._connection.execute("SELECT id FROM memory_fts WHERE memory_fts MATCH 'Lyon'").fetchall()
        assert store._connection.execute("SELECT id FROM memory_fts WHERE memory_fts MATCH 'Lille'").fetchone()[0]==new.id
    with Store('validation_person',path) as store:
        assert len(store.rows())==2
        assert store.forget_scope([new.id])=={old.id,new.id}
        store.purge([new.id])
        assert len(store.rows())==1
        assert store._connection.execute('SELECT count(*) FROM reflections').fetchone()[0]==0
        assert store._connection.execute('SELECT count(*) FROM vectors').fetchone()[0]==0
        assert store.integrity()['status']=='ok'
    raw=path.read_bytes()
    assert b'Lyon' not in raw and b'Lille' not in raw and b'fictional_vector' not in raw
    with Store('validation_person',path) as store:
        store.purge()
        assert store.integrity()['events']==0 and store.integrity()['memories']==0


def test_shared_source_forgetting_closure_and_user_isolation(tmp_path):
    with Store('validation_a',tmp_path/'validation_a.db') as a, Store('validation_b',tmp_path/'validation_b.db') as b:
        text='Je vis a Dijon et mon chat est Pixel.'
        event,_=a.record_event(request_id='validation_common_001',role='user',channel='text',content=text)
        items=[a.remember(statement=q,kind='confirmed',confidence=1,event_id=event.id,evidence_quote=q,key=k)
            for q,k in [('Je vis a Dijon','user.residence'),('mon chat est Pixel','user.pet')]]
        add(b,'Je vis a Rouen.','user.residence')
        assert a.forget_scope([items[0].id])=={i.id for i in items}
        a.purge([items[0].id])
        assert not a.rows() and len(b.rows())==1


def test_emotion_decay_expiry_and_thoughts_not_facts(tmp_path):
    with Store('validation_emotion',tmp_path/'validation_emotion.db') as store:
        engine=MoodEngine()
        assert engine.react(store,'merci').label=='chaleureuse'
        assert engine.react(store,'je suis triste').label=='attentionnee'
        store._connection.execute("UPDATE mood SET updated_at='2000-01-01T00:00:00+00:00'")
        assert engine.react(store,'').label=='calme'
        e,_=store.record_event(request_id='validation_feeling_01',role='user',channel='text',content='Je suis fatigue')
        store._connection.execute('INSERT INTO feelings VALUES(?,?,?,?)',('validation_feeling',e.id,'fatigue',time.time()-1))
        store._connection.execute('INSERT INTO reflections VALUES(?,?,?,?)',('validation_thought',e.id,'Parler doucement',time.time()-1))
        assert not store.rows()
        store.expire()
        assert store.integrity()['events']==0


def test_validation_id_required_in_tests(tmp_path):
    with pytest.raises(RuntimeError): Store('proprietaire',tmp_path/'validation.db')


def test_old_fact_not_cutoff_by_2000(tmp_path):
    with Store('validation_scale',tmp_path/'validation_scale.db') as store:
        first,_=add(store,'Mon objet ancien est un astrolabe.','user.object')
        for i in range(2100): add(store,f'Objet fictif numero {i}.',f'user.object{i}',f'validation_item_{i:05}')
        assert len(store.rows())==2101
        assert store._connection.execute("SELECT id FROM memory_fts WHERE memory_fts MATCH 'astrolabe'").fetchone()[0]==first.id


def test_model_cannot_store_nonliteral_source(tmp_path):
    session=Mock()
    session.ask.side_effect=[(json.dumps(dict(facts=[dict(quote='Je vis a Paris')],
        feeling='')),0,{}),
        (json.dumps(dict(reply='Bonjour',reflection='')),0,{})]
    search=Mock();search.candidates.return_value=[]
    memory=Memory(session,'validation_model',tmp_path/'validation_model.db',search)
    try:
        memory.answer('Bonjour',[],'Systeme',Mock())
        assert not memory.store.rows()
    finally: memory.close()


def test_forget_cancellation_changes_nothing(tmp_path):
    memory=Memory(Mock(),'validation_cancel',tmp_path/'validation_cancel.db',Mock())
    try:
        fact,_=add(memory.store,'Je vis a Rouen.','user.residence')
        _,changed=memory.forget([fact.id],lambda _:False)
        assert not changed and len(memory.store.rows())==1
    finally: memory.close()


def test_emotion_cannot_become_fact_even_when_model_approves(tmp_path):
    session=Mock()
    session.ask.side_effect=[
        (json.dumps(dict(facts=[dict(quote='Je suis triste.')],feeling='triste')),0,{}),
        ('{"valid":[true]}',0,{}),
        ('{"reply":"Je t ecoute.","reflection":"ecouter"}',0,{})]
    search=Mock();search.candidates.return_value=[]
    memory=Memory(session,'validation_emotion_guard',tmp_path/'validation_emotion_guard.db',search)
    try:
        memory.answer('Je suis triste.',[],'Systeme',Mock())
        assert not memory.store.rows()
        assert memory.store.mood()[2]=='attentionnee'
        assert memory.store._connection.execute('SELECT label FROM feelings').fetchone()[0]=='triste'
        assert memory.store._connection.execute('SELECT text FROM reflections').fetchone()[0]=='ecouter'
    finally: memory.close()


def test_incomplete_model_retry_is_bounded_and_does_not_write(tmp_path):
    session=Mock()
    session.ask.side_effect=[RuntimeError('Reponse incomplete : test'),('{"ok":true}',0,{})]
    memory=Memory(session,'validation_retry',tmp_path/'validation_retry.db',Mock())
    try:
        assert memory.ask_json('Test',{}, {})=={'ok':True}
        assert session.ask.call_count==2 and memory.store.integrity()['events']==0
        session.ask.side_effect=RuntimeError('Reponse incomplete : test')
        with pytest.raises(RuntimeError): memory.ask_json('Test',{}, {})
        assert session.ask.call_count==4
        session.ask.side_effect=RuntimeError('Guard stopped')
        with pytest.raises(RuntimeError): memory.ask_json('Test',{}, {})
        assert session.ask.call_count==5
    finally: memory.close()


@pytest.mark.parametrize('same_subject,same_property,expected_city',[(False,True,'Lyon'),(True,False,'Lyon'),(True,True,'Lille')])
def test_relation_requires_both_subject_and_property_before_overwrite(tmp_path,same_subject,same_property,expected_city):
    session=Mock();search=Mock()
    memory=Memory(session,'validation_relation',tmp_path/'validation_relation.db',search)
    try:
        add(memory.store,'Je vis a Lyon.','user.residence')
        old=memory.store.rows()[0]
        search.candidates.side_effect=[[old],[]]
        memory.ask_json=Mock(side_effect=[
            {'facts':[{'quote':'Je vis a Lille.'}],'feeling':''},
            {'valid':[True]}, {'index':0},
            {'same_subject':same_subject,'same_property':same_property},
            {'reply':'Reponse fictive','reflection':''}])
        memory.answer('Je vis a Lille.',[],'Systeme',lambda _:False)
        assert [r['statement'] for r in memory.store.rows()]==[f'Je vis a {expected_city}.']
        reply_data=memory.ask_json.call_args.args[1]
        if expected_city=='Lyon':
            assert reply_data['faits_retenus_ce_tour']==[]
            assert reply_data['corrections_ambigues_non_enregistrees']==['Je vis a Lille.']
        else:
            assert reply_data['faits_retenus_ce_tour']==['Je vis a Lille.']
    finally: memory.close()
