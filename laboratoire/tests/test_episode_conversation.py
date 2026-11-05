import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_episodic_memory import Search
from episode_conversation import Conversation
from memory_backend import create_memory
from observation import Observation

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='validation_bridge_',dir=Path(__file__).resolve().parents[1]/'logs')
        self.folder=Path(self.temp.name)
        self.observer=Observation(True,self.folder/'validation_trace',background=False)
        self.session=SimpleNamespace(observer=self.observer)
        self.memory=Conversation(self.session,'validation_bridge',self.folder/'validation.db',Search())
        self.memory.ask_json=lambda *args,**kwargs:{'feeling':'triste'}
    def tearDown(self):
        self.memory.close();self.observer.close();self.temp.cleanup()
    def turn(self,history=()):
        with patch('episode_conversation.Reader.answer',return_value={
            'reply':'Reponse fictive','reflection':'ecouter','evidence_ids':[]}):
            return self.memory.answer('Je suis triste. Mon nom est TEST_PRIVATE.',history,'system',lambda _:True)
    def test_transcript_and_temporary_emotions_are_separate(self):
        self.turn()
        self.assertEqual(len(self.memory.episodes.get(self.memory.current)['messages']),2)
        self.assertEqual(self.memory.store._connection.execute('SELECT count(*) FROM feelings').fetchone()[0],1)
        self.assertEqual(self.memory.store._connection.execute('SELECT count(*) FROM memories').fetchone()[0],0)
        self.memory.store._connection.execute('UPDATE feelings SET expires=0')
        self.memory.store._connection.execute('UPDATE reflections SET expires=0')
        self.memory.store.expire()
        self.assertEqual(self.memory.store._connection.execute('SELECT count(*) FROM feelings').fetchone()[0],0)
        self.assertIsNotNone(self.memory.episodes.get(self.memory.current))
    def test_cancel_and_accept_forgetting_purge_state_and_trace(self):
        self.turn();identity=self.memory.current
        self.observer.begin_turn('TEST_PRIVATE','text');self.observer.flush()
        self.assertFalse(self.memory.forget(None,lambda _:False)[1])
        self.assertIsNotNone(self.memory.episodes.get(identity))
        self.assertTrue(self.memory.forget(None,lambda _:True)[1])
        self.assertIsNone(self.memory.episodes.get(identity))
        self.assertNotIn('TEST_PRIVATE',self.observer.path.read_text())
        for table in ['feelings','reflections','events']:
            self.assertEqual(self.memory.store._connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertIsNone(self.memory.current)
        self.assertEqual(self.memory.last_result,{})
        self.assertEqual(self.memory.last_review,{})
    def test_correction_requests_history_reset(self):
        self.turn();identity=self.memory.current
        answer,reset=self.memory.correct_source(identity,1,[{'role':'user','content':'Correction explicite'}],lambda _:True)
        self.assertTrue(reset)
        self.assertEqual(self.memory.episodes.get(identity)['messages'][0]['content'],'Correction explicite')
        self.assertEqual(self.memory.store._connection.execute('SELECT count(*) FROM feelings').fetchone()[0],0)
    def test_inactive_backend_cannot_open_any_memory(self):
        with patch('persistent_memory.Memory') as legacy:
            with self.assertRaises(ValueError):create_memory(self.session,backend='unused')
            legacy.assert_not_called()
    def test_emotions_and_intentions_do_not_grow_model_context(self):
        self.turn()
        event_id=self.memory.store._connection.execute('SELECT id FROM events LIMIT 1').fetchone()[0]
        import time
        for i in range(100):
            self.memory.store._connection.execute('INSERT INTO feelings VALUES(?,?,?,?)',
                (str(i),event_id,'triste',time.time()+1000))
            self.memory.store._connection.execute('INSERT INTO reflections VALUES(?,?,?,?)',
                (str(i),event_id,'ecouter',time.time()+1000))
        with patch('episode_conversation.Reader.answer',return_value={
            'reply':'Reponse','reflection':'','evidence_ids':[]}) as reader:
            self.memory.answer('Bonjour',[],'system',lambda _:True)
        auxiliary=reader.call_args.args[3]
        self.assertEqual(len(auxiliary['emotions_temporaires']),2)
        self.assertEqual(len(auxiliary['intentions_non_factuelles']),2)
    def test_experimental_backend_rejects_real_identity(self):
        with self.assertRaises(ValueError):create_memory(self.session,'proprietaire',self.folder/'other.db',Search(),'episodic_validation')
        self.assertFalse((self.folder/'other.db').exists())

if __name__=='__main__':unittest.main()
