import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from episodic_memory import Episodes,Conflict,Reader
from test_episodic_memory import Search,DATE,turns
from memory_forgetting import prepare,expand
from reviewed_memory_reader import ReviewedReader

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='validation_release_unit_',dir=Path(__file__).resolve().parents[1]/'logs')
        self.store=Episodes(Path(self.temp.name)/'memory.db','validation_release_unit',Search())
    def tearDown(self):self.store.close();self.temp.cleanup()
    def test_precise_deletion_retains_independent_turns_and_reindexes(self):
        identity=self.store.add(DATE,turns('ancien')+[{'role':'assistant','content':'ancien confirme'}]+turns('nouveau'))
        self.store.apply_forgetting([dict(id=identity,revision=1,keep=[2])],self.store.version())
        self.assertEqual(self.store.get(identity)['messages'],turns('nouveau'))
        self.assertEqual(self.store.get(identity)['revision'],2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM passages').fetchone()[0],1)
    def test_archive_change_invalidates_complete_plan(self):
        a=self.store.add(DATE,turns('ancien'));b=self.store.add(DATE,turns('nouveau'))
        version=self.store.version();self.store.add(DATE,turns('ajout pendant confirmation'))
        with self.assertRaises(Conflict):self.store.apply_forgetting([
            dict(id=a,revision=1,keep=[]),dict(id=b,revision=1,keep=[])],version)
        self.assertIsNotNone(self.store.get(a));self.assertIsNotNone(self.store.get(b))
    def test_invalid_plan_never_removes_first_source(self):
        a=self.store.add(DATE,turns('ancien'));b=self.store.add(DATE,turns('nouveau'))
        for invalid in [[20],[-1],[True],[0,0]]:
            with self.assertRaises(ValueError):self.store.apply_forgetting([
                dict(id=a,revision=1,keep=[]),dict(id=b,revision=1,keep=invalid)],self.store.version())
            self.assertIsNotNone(self.store.get(a))
    def test_planner_visits_every_source_without_semantic_retrieval(self):
        for i in range(15):self.store.add(DATE,turns('source '+str(i)))
        with patch.object(self.store,'retrieve',side_effect=AssertionError('Must scan all')), \
             patch('memory_forgetting.ask',side_effect=[{'subject':'le sujet'}]+[{'remove':[]}]*15) as ask:
            proposal=prepare(object(),self.store,'Oublie le sujet')
        self.assertEqual(ask.call_count,16);self.assertEqual(proposal['scanned'],15)
        self.assertEqual(proposal['plan'],[])
    def test_ambiguity_does_not_propose_or_apply_deletion(self):
        identity=self.store.add(DATE,turns('ancien'))
        with patch('memory_forgetting.ask',return_value={'subject':''}):
            proposal=prepare(object(),self.store,'Oublie ca')
        self.assertTrue(proposal['ambiguous']);self.assertEqual(proposal['plan'],[])
        self.assertIsNotNone(self.store.get(identity))
    def test_assistant_echo_cannot_survive_removed_user_turn(self):
        messages=turns('ancien')+[{'role':'assistant','content':'ancien'}]+turns('nouveau')
        self.assertEqual(expand(messages,[0]),{0,1})
        with self.assertRaises(ValueError):expand(messages,[True])
    def test_empty_archive_uses_measured_reader_without_extra_model_calls(self):
        with patch('reviewed_memory_reader.ask',side_effect=AssertionError('No extra call')), \
             patch('reviewed_memory_reader.Reader.answer',return_value={'reply':'Texte'}) as reader:
            self.assertEqual(ReviewedReader(SimpleNamespace(),self.store).answer('Question')['reply'],'Texte')
        reader.assert_called_once()
    def test_configured_backend_uses_explicit_validation_database(self):
        import memory_backend
        folder=Path(self.temp.name);(folder/'config').mkdir()
        (folder/'config/memory_backend.json').write_text('{"backend":"v5_context"}')
        with patch.object(memory_backend,'ROOT',folder),patch('v5_context_memory.V5Conversation') as factory:
            memory_backend.create_memory(object(),'validation_factory',folder/'other.db',Search())
            self.assertFalse(factory.call_args.kwargs['allow_personal'])
            with self.assertRaises(ValueError):memory_backend.create_memory(object(),'validation_factory')
    def test_large_archive_reranking_is_read_only(self):
        identities=[self.store.add(DATE,turns('source '+str(i))) for i in range(8)]
        with patch('reviewed_memory_reader.ask',return_value={'kind':'specific_fact','ids':[identities[0]]}), \
             patch('reviewed_memory_reader.Reader.answer',return_value={'reply':'Texte','sources':[]}):
            result=ReviewedReader(SimpleNamespace(),self.store).answer('Question')
        self.assertEqual(result['candidate_count'],8);self.assertEqual(self.store.version(),8)
    def test_personal_permission_never_bypasses_test_guard(self):
        with self.assertRaises(ValueError):
            Episodes(Path(self.temp.name)/'forbidden.db','proprietaire',Search(),allow_personal=True)
        self.assertFalse((Path(self.temp.name)/'forbidden.db').exists())
    def test_inactive_backends_are_rejected_without_opening_memory(self):
        from memory_backend import create_memory
        path=Path(self.temp.name)/'unused.db'
        with self.assertRaises(ValueError):create_memory(object(),'validation_rejected',path,Search(),backend='unused')
        self.assertFalse(path.exists())
    def test_reranker_cannot_invent_a_source(self):
        for i in range(8):self.store.add(DATE,turns('source '+str(i)))
        with patch('reviewed_memory_reader.ask',return_value={'kind':'specific_fact','ids':['inventee']}):
            with self.assertRaises(ValueError):ReviewedReader(SimpleNamespace(),self.store).answer('Question')
        self.assertEqual(self.store.version(),8)
    def test_reranking_preserves_preference_scope_guard(self):
        self.store.add(DATE,turns('Pour ce soir seulement, je veux du silence.'))
        class Session:
            def __init__(self):self.calls=[];self.responses=[
                {'requires_general_preference':True,'support':[]},
                {'reply':'Preference generale inconnue.','evidence_ids':[]}]
            def ask(self,messages,**kwargs):
                self.calls.append(messages);return json.dumps(self.responses.pop(0)),None,{}
        session=Session();result=Reader(session,self.store,query_kind='general_preference').answer('Ma preference generale ?')
        self.assertEqual(len(session.calls),2)
        self.assertEqual(result['admitted_ids'],[])
        self.assertEqual(result['decision']['route'],'general_preference')
    def test_long_confirmation_is_scrollable_and_stop_cancels(self):
        import subprocess
        result=subprocess.run([sys.executable,'-B','tests/check_memory_confirmation.py'],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
