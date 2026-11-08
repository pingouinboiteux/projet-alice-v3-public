"""Offline contracts, with injected validation data and no application startup."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'laboratoire/scripts')]
# The personality is file-backed in production; tests never read that file.
personality = type(sys)('alice_personality')
personality.PERSONALITY = 'validation_personality'
with patch.dict(sys.modules, {'alice_personality': personality}):
    from integrations.laboratoire import remote_dialogue as remote


def message(source='twitch', author='validation_viewer'):
    return remote.RemoteText(source, author, 'validation_question')


class RemoteDialogueTests(unittest.TestCase):
    def model(self, reply='validation_reply'):
        return Mock(return_value=(json.dumps({'reply': reply}), None, None))

    def test_identity_both_orders(self):
        names = ['remote_dialogue', 'integrations.laboratoire.remote_dialogue']
        for order in (names, names[::-1]):
            code = (
                'import sys, types, importlib; '
                f'sys.path[:0] = {[str(ROOT), str(ROOT / "laboratoire/scripts")]!r}; '
                'p=types.ModuleType("alice_personality"); p.PERSONALITY="validation_personality"; '
                'sys.modules["alice_personality"]=p; '
                f'a=importlib.import_module({order[0]!r}); b=importlib.import_module({order[1]!r}); '
                'assert a is b; assert a.RemoteText is b.RemoteText; '
                'assert a.RemoteDialogue is b.RemoteDialogue; assert a.require_local is b.require_local'
            )
            subprocess.run([sys.executable, '-B', '-c', code], check=True)

    def test_envelope_and_local_gate(self):
        for changes in ({'source':'text'}, {'author':''}, {'author':'a'*81},
                        {'text':''}, {'text':'x'*2001}, {'display_name':None},
                        {'display_name':'a'*81}):
            values = dict(source='twitch', author='validation_viewer', text='validation_text')
            values.update(changes)
            with self.assertRaises(ValueError):
                remote.RemoteText(**values)
        for source in ('text', 'voice'):
            remote.require_local(source)
        for source in ('discord', 'twitch', ''):
            with self.assertRaises(PermissionError):
                remote.require_local(source)
        model = self.model()
        with self.assertRaises(ValueError):
            remote.RemoteDialogue(model).answer(object())
        model.assert_not_called()

    def test_schema_filter_and_fallback(self):
        model, output = self.model('x'*700), Mock(return_value='validation_filtered')
        self.assertEqual(remote.RemoteDialogue(model, output).answer(message()), 'validation_filtered')
        output.assert_called_once_with('x'*600)
        self.assertEqual(model.call_args.kwargs, {'response_schema': remote.SCHEMA})
        self.assertEqual(remote.RemoteDialogue(self.model(), lambda _: '').answer(message()),
                         'Je prefere ne pas prononcer cette reponse.')
        for raw in ('[]', '{"reply":1}', '{"reply":"x","extra":1}', 'invalid'):
            with self.assertRaises(ValueError):
                remote.RemoteDialogue(Mock(return_value=(raw,None,None))).answer(message())

    def test_history_isolation_bounds_expiration_and_discard(self):
        model = self.model()
        dialogue = remote.RemoteDialogue(model)
        with patch.object(remote.time, 'monotonic', return_value=0):
            for _ in range(5):
                dialogue.answer(message())
            self.assertEqual(len(dialogue.histories[('twitch','validation_viewer')][1]), 6)
            dialogue.answer(message('discord'))
            self.assertEqual(len(model.call_args.args[0]), 2)
            dialogue.discard_reply(message(), 'wrong')
            self.assertEqual(len(dialogue.histories[('twitch','validation_viewer')][1]), 6)
            dialogue.discard_reply(message(), 'validation_reply')
            self.assertEqual(len(dialogue.histories[('twitch','validation_viewer')][1]), 5)
        with patch.object(remote.time, 'monotonic', return_value=301):
            dialogue.answer(message('discord','validation_new'))
            self.assertEqual(len(dialogue.histories), 1)
            for i in range(40):
                dialogue.answer(message(author=f'validation_{i}'))
            self.assertEqual(len(dialogue.histories), 32)
            self.assertNotIn(('twitch','validation_0'), dialogue.histories)
        dialogue.clear()
        self.assertFalse(dialogue.histories)

    def test_injected_store_library_scene_and_delivery(self):
        model, store, library, scene = self.model(), Mock(), Mock(), Mock()
        store.context.return_value = ([{'role':'user','content':'validation_old'}]*30, False)
        library.context.return_value = ['validation_document']
        scene.snapshot.return_value = ['validation_event']
        dialogue = remote.RemoteDialogue(model, store=store, library=library, scene=scene)
        entry = message()
        reply = dialogue.answer(entry)
        store.record.assert_not_called()
        store.delivered.assert_not_called()
        prompt = model.call_args.args[0]
        self.assertIn('validation_event', str(prompt))
        self.assertIn('validation_document', str(prompt))
        self.assertIn('premier_contact_du_jour', str(prompt))
        self.assertEqual(len(dialogue.histories[(entry.source,entry.author)][1]),24)
        dialogue.delivered(entry, reply)
        store.record.assert_called_once_with(entry.source, entry.author, entry.text, reply)
        store.delivered.assert_called_once_with(entry.source, entry.author)
        scene.snapshot.reset_mock()
        dialogue.answer(message('discord'))
        scene.snapshot.assert_not_called()
        self.assertNotIn('validation_event', str(model.call_args.args[0]))


if __name__ == '__main__':
    unittest.main()
