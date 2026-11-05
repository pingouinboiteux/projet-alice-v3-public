"""Natural language must not bypass intent classification through a verb prefix."""
from unittest.mock import patch
import pytest
from memory_backend import is_memory_control
import unittest
import test_episode_conversation as bridge

@pytest.mark.parametrize('text',[
    'Supprime le fichier test.txt dans ton atelier.',
    'Efface uniquement le commentaire de mon fichier.',
    'Oublie cette idee, parlons du prochain stream.',
    'Oublie ce que je t ai dit de mon ancien travail.',
])
def test_natural_language_is_classified_before_memory_management(text):
    assert not is_memory_control(text)

def test_explicit_memory_commands_remain_available():
    assert is_memory_control('/memoire')
    assert is_memory_control('/oublier-tout')

class MemoryDispatchTests(unittest.TestCase):
    setUp=bridge.BridgeTests.setUp
    tearDown=bridge.BridgeTests.tearDown
    def test_dialogue_cannot_reinterpret_a_refused_action_as_forgetting(self):
        with patch.object(self.memory,'forget_subject') as forget,patch(
                'episode_conversation.Reader.answer',return_value={
                    'reply':'Parlons de la suite.','reflection':'explorer','evidence_ids':[]}):
            reply,forgotten=self.memory.answer('Oublie cette idee, discutons.',[],'system',lambda _:True)
        forget.assert_not_called()
        self.assertFalse(forgotten)
        self.assertEqual(reply,'Parlons de la suite.')
