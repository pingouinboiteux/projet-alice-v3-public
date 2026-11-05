"""Synthetic memory only; no model, user memory or external channel."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_episodic_memory import Search, turns
from episodic_memory import Episodes
from v5_context_memory import V5Episodes, V5Reader
from unittest.mock import patch
import test_episode_conversation as bridge
from v5_context_memory import V5Conversation
from memory_backend import create_memory

class V5ConversationTests(bridge.BridgeTests):
    def setUp(self):
        with patch.object(bridge,'Conversation',V5Conversation):super().setUp()
    def test_factory_opens_only_explicit_synthetic_database(self):
        with self.assertRaises(ValueError):create_memory(self.session,'validation_v5',backend='v5_context')
        with self.assertRaises(ValueError):create_memory(self.session,'other',self.folder/'other.db',Search(),'v5_context')
        memory=create_memory(self.session,'validation_v5',self.folder/'v5.db',Search(),'v5_context')
        try:self.assertIsInstance(memory,V5Conversation)
        finally:memory.close()

class V5SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='validation_v5_',dir=Path(__file__).resolve().parents[1]/'logs')
        self.path=Path(self.tmp.name)/'validation.db'
        self.store=V5Episodes(self.path,'validation_v5',Search())
        self.target=self.store.add('2026-01-01T12:00:00Z',turns('Mon dossier Zorvex contient le devis original.'))
        self.assistant_only=self.store.add('2026-01-02T12:00:00Z',[
            {'role':'user','content':'Bonjour'}, {'role':'assistant','content':'Zorvex est bleu.'}])
        for day in range(3,24):
            self.store.add(f'2026-01-{day:02d}T12:00:00Z',turns('Discussion du jour sur les jeux.'))
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def test_lexical_supplement_preserves_baseline_and_complete_source(self):
        before=self.store.version();source=self.store.get(self.target)
        baseline=Episodes.candidates(self.store,'Zorvex',12)
        self.assertNotIn(self.target,[e['id'] for e in baseline])
        result=self.store.candidates('Zorvex')
        self.assertEqual(result[:12],baseline)
        self.assertIn(self.target,[e['id'] for e in result])
        self.assertNotIn(self.assistant_only,[e['id'] for e in result[12:]])
        self.assertEqual(len({e['id'] for e in result}),len(result))
        self.assertEqual(self.store.get(self.target),source)
        self.assertEqual(self.store.version(),before)
    def test_corrected_and_forgotten_sources_are_not_reintroduced(self):
        self.store.correct(self.target,1,'2026-01-01T12:00:00Z',turns('Le dossier porte un autre nom.'))
        self.assertNotIn(self.target,[e['id'] for e in self.store.candidates('Zorvex')])
        self.store.forget_many([(self.target,2)])
        self.assertIsNone(self.store.get(self.target))
    def test_original_schema_can_reopen_candidate(self):
        other=Episodes(self.path,'validation_v5',Search())
        try:self.assertEqual(other.get(self.target),self.store.get(self.target))
        finally:other.close()
    def test_budget_drops_optional_hints_before_baseline(self):
        import json
        session=SimpleNamespace(count_tokens=lambda messages:len(json.loads(messages[1]['content'])['indices'])*450)
        reader=V5Reader(session,self.store)
        result=reader.candidate_sources('Zorvex')
        self.assertEqual(result,Episodes.candidates(self.store,'Zorvex',12))
    def test_invalid_limits(self):
        for limit in (True,0,25,1.5):
            with self.assertRaises(ValueError):self.store.candidates('Zorvex',limit)

if __name__=='__main__':unittest.main()
