import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat
from codex_link import action_reply


class ConversationIntegration(unittest.TestCase):
    def test_code_request_is_refused_without_task_or_dialogue_inference(self):
        session = MagicMock()
        session.temp = None
        result = {'status': 'completed', 'answer': 'Fichier cree.', 'changed_files': ['bonjour.txt']}
        with patch.object(sys, 'argv', ['chat.py', '--voice', '--codex']), \
             patch('builtins.input', side_effect=['/faire Cree bonjour.txt', '/quitter']), \
             patch('chat.Session', return_value=session) as factory, \
             patch('voice_link.Voice') as voice, \
             patch('codex_link.run_task', return_value=result) as task:
            chat.main()
        factory.assert_called_once_with(allow_game=False, context_window=16384)
        task.assert_not_called()
        voice.return_value.speak.assert_not_called()
        session.ask.assert_not_called()
        session.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
