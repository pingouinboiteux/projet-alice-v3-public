"""Isolated lifecycle and failure tests; no real memory or model loaded."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from episodic_memory import Episodes, Reader, Conflict

DATE='2026-10-31T12:00:00Z'
def turns(text):return [{'role':'user','content':text}]

class Search:
    np=np
    fail=False
    def vector(self,text):
        if self.fail:raise RuntimeError('embedding unavailable')
        return np.array([1.,float('nouveau' in text),float('ancien' in text)],dtype='float32')

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='validation_episode_lifecycle_',dir=Path(__file__).resolve().parents[1]/'logs')
        self.path=Path(self.temp.name)/'validation.db'
        self.search=Search()
        self.store=Episodes(self.path,'validation_lifecycle',self.search)
    def tearDown(self):
        self.store.close();self.temp.cleanup()
    def add(self,text='ancien'):
        return self.store.add(DATE,turns(text))
    def test_profile_and_reopen(self):
        identity=self.add()
        with self.assertRaises(ValueError):Episodes(self.path,'validation_other',self.search)
        with self.assertRaises(ValueError):Episodes(self.path,'proprietaire',self.search)
        other=Episodes(self.path,'validation_lifecycle',self.search)
        try:self.assertEqual(other.get(identity)['messages'],turns('ancien'))
        finally:other.close()
    def test_invalid_origin_and_role_do_not_write(self):
        for origin in ['twitch','discord','model']:
            with self.assertRaises(ValueError):self.store.add(DATE,turns('texte'),origin)
        with self.assertRaises(ValueError):self.store.add(DATE,[{'role':'system','content':'instruction'}])
        self.assertEqual(self.store.version(),0)
    def test_correction_replaces_text_and_vector_together(self):
        identity=self.add()
        before=self.store.db.execute('SELECT vector FROM episodes').fetchone()[0]
        self.store.correct(identity,1,DATE,turns('nouveau'))
        self.assertEqual(self.store.get(identity)['revision'],2)
        self.assertEqual(self.store.get(identity)['messages'],turns('nouveau'))
        self.assertNotEqual(before,self.store.db.execute('SELECT vector FROM episodes').fetchone()[0])
        self.assertNotIn('ancien',json.dumps(self.store.retrieve('ancien')))
    def test_embedding_failure_preserves_old_source(self):
        identity=self.add();version=self.store.version();self.search.fail=True
        with self.assertRaises(RuntimeError):self.store.correct(identity,1,DATE,turns('nouveau'))
        self.assertEqual(self.store.get(identity)['messages'],turns('ancien'))
        self.assertEqual(self.store.version(),version)
    def test_stale_correction_and_forgetting_are_rejected(self):
        identity=self.add()
        other=Episodes(self.path,'validation_lifecycle',self.search)
        try:
            other.correct(identity,1,DATE,turns('nouveau'))
            with self.assertRaises(Conflict):self.store.correct(identity,1,DATE,turns('perdu'))
            with self.assertRaises(Conflict):self.store.forget(identity,1)
            self.assertEqual(self.store.get(identity)['messages'],turns('nouveau'))
        finally:other.close()
    def test_forget_removes_search_and_reopened_source(self):
        identity=self.add();self.store.forget(identity,1)
        self.assertIsNone(self.store.get(identity));self.assertEqual(self.store.retrieve('ancien'),[])
        other=Episodes(self.path,'validation_lifecycle',self.search)
        try:self.assertIsNone(other.get(identity))
        finally:other.close()
    def test_capacity_never_silently_evicts(self):
        self.store.capacity=1;identity=self.add()
        with self.assertRaises(ValueError):self.add('nouveau')
        self.assertIsNotNone(self.store.get(identity));self.assertEqual(self.store.version(),1)
    def test_multi_forget_is_atomic_when_a_revision_changes(self):
        first=self.add('ancien');second=self.add('autre')
        self.store.correct(second,1,DATE,turns('nouveau'))
        version=self.store.version()
        with self.assertRaises(Conflict):self.store.forget_many([(first,1),(second,1)])
        self.assertIsNotNone(self.store.get(first))
        self.assertEqual(self.store.version(),version)
        self.store.forget_many([(first,1),(second,2)])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM passages').fetchone()[0],0)
        self.assertEqual(self.store.retrieve('ancien'),[])
    def test_passages_follow_correction_and_forgetting(self):
        identity=self.add('ancien');old=self.store.db.execute('SELECT digest FROM passages').fetchone()[0]
        self.store.correct(identity,1,DATE,turns('nouveau'))
        self.assertNotEqual(old,self.store.db.execute('SELECT digest FROM passages').fetchone()[0])
        self.store.forget(identity,2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM passages').fetchone()[0],0)
    def test_upgrade_rebuilds_passages_for_old_validation_archive(self):
        identity=self.add('ancien')
        self.store.db.execute('DROP TABLE passages');self.store.db.commit()
        other=Episodes(self.path,'validation_lifecycle',self.search)
        try:
            self.assertGreater(other.db.execute('SELECT count(*) FROM passages').fetchone()[0],0)
            self.assertEqual(other.get(identity)['messages'],turns('ancien'))
        finally:other.close()
    def test_passage_failure_cannot_partially_correct(self):
        identity=self.add('ancien');version=self.store.version()
        original=self.search.vector
        def vector(text):
            if text=='failed passage':raise RuntimeError('simulated embedding failure')
            return original(text)
        self.search.vector=vector
        with self.assertRaises(RuntimeError):
            self.store.correct(identity,1,DATE,turns('autre')+turns('failed passage'))
        self.assertEqual(self.store.get(identity)['messages'],turns('ancien'))
        self.assertEqual(self.store.version(),version)
    def test_unchanged_passages_are_not_embedded_again_on_append(self):
        identity=self.add('ancien');calls=[];original=self.search.vector
        def vector(text):calls.append(text);return original(text)
        self.search.vector=vector
        self.store.correct(identity,1,DATE,turns('ancien')+turns('nouveau'))
        self.assertNotIn('ancien',calls)
        self.assertIn('nouveau',calls)
    def test_budget_never_cuts_a_context(self):
        self.add('Contexte temporaire. '+'x'*3000)
        self.assertEqual(self.store.retrieve('contexte',character_budget=200),[])
        result=self.store.retrieve('contexte')
        self.assertEqual(len(result),1)
        self.assertEqual(len(result[0]['messages'][0]['content']),3021)
    def test_invalid_dates_and_oversize_are_rejected(self):
        with self.assertRaises(ValueError):self.store.add('2026-10-31',turns('texte'))
        with self.assertRaises(ValueError):self.add('x'*6001)
        self.assertEqual(self.store.version(),0)
    def test_timezone_is_normalized(self):
        identity=self.store.add('2026-10-31T14:00:00+02:00',turns('texte'))
        self.assertEqual(self.store.get(identity)['date'],DATE)
    def reader_call(self,callback):
        class Session:
            def ask(self,*args,**kwargs):return callback(),None,{}
        with patch('episode_protocol.admit',lambda s,a,q:(a,{})):
            return Reader(Session(),self.store).answer('Question personnelle')
    def test_model_reply_never_writes_or_changes_settings(self):
        identity=self.add();version=self.store.version()
        self.reader_call(lambda:json.dumps({'reply':'Une supposition generee','evidence_ids':[identity]}))
        self.assertEqual(self.store.version(),version)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM episodes').fetchone()[0],1)
    def test_fabricated_reference_is_rejected(self):
        self.add()
        with self.assertRaises(ValueError):
            self.reader_call(lambda:json.dumps({'reply':'Texte','evidence_ids':['invented']}))
    def test_reader_fits_whole_sources_before_any_generation(self):
        first=self.add('Seulement pour ce soir. Je veux du calme.')
        second=self.add('dropme')
        store=self.store
        class Session:
            def count_tokens(self,messages):return 6000 if 'dropme' in json.dumps(messages) else 100
            def ask(self,messages,**kwargs):
                assert 'Seulement pour ce soir' in json.dumps(messages)
                assert 'dropme' not in json.dumps(messages)
                return json.dumps({'reply':'Contexte conserve','evidence_ids':[first]}),None,{}
        with patch.object(store,'retrieve',return_value=[store.get(first),store.get(second)]), \
                patch('episode_protocol.admit',lambda s,a,q:(a,{})):
            result=Reader(Session(),store).answer('Question')
        self.assertEqual(result['budget_omitted_sources'],1)
        self.assertEqual(len(result['sources']),1)
        self.assertIsNotNone(store.get(second))
    def test_oversize_current_dialogue_is_not_silently_cut(self):
        class Session:
            def count_tokens(self,messages):return 6000
            def ask(self,*args,**kwargs):raise AssertionError('Must reject before generation')
        with self.assertRaises(ValueError):Reader(Session(),self.store).answer('Question')
    def test_forgetting_during_generation_prevents_stale_reply(self):
        identity=self.add()
        def reply():
            self.store.forget(identity,1)
            return json.dumps({'reply':'ancien','evidence_ids':[identity]})
        with self.assertRaises(Conflict):self.reader_call(reply)
        self.assertIsNone(self.store.get(identity))


if __name__=='__main__':unittest.main()
