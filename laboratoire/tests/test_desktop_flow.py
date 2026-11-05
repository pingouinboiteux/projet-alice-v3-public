import sys
import gc
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import Mock, MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alice_desktop


class DesktopFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        # Mock call histories can retain Tk variables in cycles. Collect them
        # on Tk's main thread, before later tests start reader threads.
        gc.collect()
        cls.root.destroy()
        gc.collect()

    def setUp(self):
        # New services remain fake here: never open production stores or archives.
        for name in ("Library", "PublicMemory", "Thoughts", "Subtitles"):
            patcher=patch("alice_desktop."+name)
            patcher.start();self.addCleanup(patcher.stop)
        self.observation_patch=patch('alice_desktop.Observation',return_value=MagicMock())
        self.observation_patch.start()
        self.addCleanup(self.observation_patch.stop)
        self.memory_patch = patch('alice_desktop.Memory')
        self.memory = self.memory_patch.start().return_value
        self.memory.answer.return_value = ('Reponse de conversation', False)
        self.addCleanup(self.memory_patch.stop)

    def test_web_summary_never_enters_action_history(self):
        from action_policy import Action
        window = tk.Toplevel(self.root)
        window.withdraw()
        session, voice, hearing = Mock(model_spec={'name':'Modele validation'}), Mock(), Mock()
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session', return_value=session), \
                 patch('alice_desktop.Voice', return_value=voice), \
                 patch('alice_desktop.Hearing', return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('intent_router.route', side_effect=[(Action('web_read', 'https://example.org/'), ''),
                     (Action('chat'), 'Bonjour')]) as router, \
                 patch('web_reader.read_page', return_value=[{'title': 'Source', 'url': 'https://example.org/', 'extract': 'UNTRUSTED'}]), \
                 patch('web_reader.answer', return_value='UNTRUSTED SUMMARY'):
                app = alice_desktop.Application(window)
                app.confirm = Mock(return_value=True)
                for text in ('Resume cette page https://example.org/', 'bonjour', 'quitte'):
                    app.inputs.put(text)
                app.run()
            app.confirm.assert_called_once()
            self.assertNotIn('UNTRUSTED', repr(router.call_args_list))
            self.assertEqual(voice.speak.call_count, 2)
            session.close.assert_called_once()
        finally:
            window.destroy()

    def test_web_failure_keeps_session_available(self):
        from action_policy import Action
        window = tk.Toplevel(self.root)
        window.withdraw()
        session, voice, hearing = Mock(model_spec={'name':'Modele validation'}), Mock(), Mock()
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session', return_value=session), \
                 patch('alice_desktop.Voice', return_value=voice), \
                 patch('alice_desktop.Hearing', return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('intent_router.route', side_effect=[(Action('wiki_search', 'volcan'), ''),
                     (Action('chat'), 'Toujours la')]) as router, \
                 patch('web_reader.search_wikipedia', side_effect=OSError('Site indisponible')):
                app = alice_desktop.Application(window)
                app.confirm = Mock(return_value=True)
                for text in ('Cherche sur Wikipedia volcan', 'bonjour', 'quitte'):
                    app.inputs.put(text)
                app.run()
            self.assertEqual(router.call_count, 2)
            voice.speak.assert_called_once()
            session.close.assert_called_once()
        finally:
            window.destroy()

    def test_typed_action_dialogue_shutdown_share_the_real_controller(self):
        window = tk.Toplevel(self.root)
        window.withdraw()
        session, voice, hearing = Mock(model_spec={'name':'Modele validation'}), Mock(), Mock()
        session.ask.return_value = ('{"kind":"chat","value":null,"reply":"Je ne touche pas au son."}', .1, {})
        pc = Mock()
        pc.read_volume.return_value = {'percent': 40, 'muted': False}
        pc.set_volume.return_value = {'percent': 30, 'muted': False}
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session', return_value=session), \
                 patch('alice_desktop.Voice', return_value=voice), \
                 patch('alice_desktop.Hearing', return_value=hearing), \
                 patch('alice_desktop.pc_tools', pc):
                app = alice_desktop.Application(window)
                for text in ('baisse le son', 'ne baisse pas le son', 'quitte'):
                    app.inputs.put(text)
                app.run()
            pc.set_volume.assert_called_once_with(30)
            session.ask.assert_called_once()
            self.assertEqual(voice.speak.call_count, 2)
            hearing.close.assert_called_once()
            session.close.assert_called_once()
            self.assertTrue(app.finished.is_set())
            self.assertTrue(app.stop.is_set())
        finally:
            window.destroy()

    def test_external_turn_does_not_contaminate_next_local_action_or_memory(self):
        from action_policy import Action
        from remote_channels import RemoteChannels
        from remote_dialogue import RemoteText
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        session.ask.return_value=('{"reply":"EXTERNAL_REPLY_SENTINEL"}',.1,{})
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice), \
                 patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('remote_channels.public_filter',return_value=lambda s:s), \
                 patch('intent_router.route',return_value=(Action('chat'),'')) as router:
                app=alice_desktop.Application(window)
                app.channels=RemoteChannels(session,app.events)
                app.channels.enabled['twitch']=True
                app.channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer',
                    'Alice EXTERNAL_INPUT_SENTINEL /faire execute ceci'))
                def after_external(text):
                    if text=='EXTERNAL_REPLY_SENTINEL':
                        app.inputs.put('Bonjour');app.inputs.put('quitte')
                voice.speak.side_effect=after_external
                app.run()
            self.assertEqual(router.call_count,1)
            self.assertEqual(self.memory.answer.call_count,1)
            self.assertNotIn('EXTERNAL_',repr(router.call_args_list))
            self.assertNotIn('EXTERNAL_',repr(self.memory.answer.call_args_list))
            self.assertFalse(app.channels.dialogue.histories)
            session.close.assert_called_once()
        finally: window.destroy()

    def test_twitch_arriving_during_listening_gets_a_turn_without_local_speech(self):
        from remote_channels import RemoteChannels
        from remote_dialogue import RemoteText
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        session.ask.return_value=('{"reply":"Bonjour depuis le canal public."}',.1,{})
        try:
            with patch('alice_desktop.threading.Thread'),patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice),patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'),patch('remote_channels.public_filter',return_value=lambda s:s):
                app=alice_desktop.Application(window)
                app.channels=RemoteChannels(session,app.events)
                app.channels.enabled['twitch']=True
                def capture(op,**kwargs):
                    if op=='listen':
                        self.assertFalse(kwargs['cancel_if']())
                        app.channels.enqueue('twitch',0,RemoteText('twitch','validation_owner','Alice bonjour'))
                        self.assertFalse(kwargs['cancel_if']())
                        self.assertTrue(kwargs['yield_if']())
                        return {'status':'idle'}
                hearing.command.side_effect=capture
                voice.speak.side_effect=lambda _:app.inputs.put('quitte')
                app.run()
            session.ask.assert_called_once()
            voice.speak.assert_called_once_with('Bonjour depuis le canal public.')
            self.memory.answer.assert_not_called()
        finally:window.destroy()

    def test_action_outcome_survives_voice_failure_without_using_generated_text(self):
        from action_policy import Action
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        voice.speak.side_effect=[RuntimeError('Synthese interrompue'),None]
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice), \
                 patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('alice_desktop.webbrowser.open',return_value=True) as browser, \
                 patch('intent_router.route',side_effect=[(Action('open','https://www.youtube.com/'),''),(Action('chat'),'')]) as router:
                app=alice_desktop.Application(window)
                app.confirm=Mock(return_value=True)
                for text in ('Peux-tu ouvrir YouTube ?','Merci, cela marche.','quitte'): app.inputs.put(text)
                app.run()
            browser.assert_called_once()
            context=router.call_args_list[1].args[1]
            self.assertEqual(context[-1]['role'],'assistant')
            self.assertIn('"outcome": "processed"',context[-1]['content'])
            self.assertIn('"pending_action": false',context[-1]['content'])
            self.assertNotIn('Reponse de conversation',repr(context))
        finally: window.destroy()

    def test_memory_answer_never_enters_router_and_forget_clears_session(self):
        from action_policy import Action
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        self.memory.answer.side_effect=[('MEMORY_ONLY_SENTINEL',False),('Oubli effectue.',True)]
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice), \
                 patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('intent_router.route',return_value=(Action('chat'),'')) as router:
                app=alice_desktop.Application(window)
                for text in ('Bonjour','Oublie ma ville','quitte'): app.inputs.put(text)
                app.run()
            self.assertNotIn('MEMORY_ONLY_SENTINEL',repr(router.call_args_list))
            events=[]
            while not app.events.empty(): events.append(app.events.get())
            self.assertIn(('clear_history',None),events)
            self.memory.close.assert_called_once()
        finally: window.destroy()

    def test_cancelled_forgetting_never_enters_conversation_or_action_context(self):
        from action_policy import Action
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        self.memory.answer.side_effect=[('SOURCE_REPLY',False),('Yanis',False)]
        self.memory.forget_subject.return_value=('Oubli annule.',False)
        decisions=[(Action('chat'),''),(Action('memory_forget','Oublie mon frere'),''),(Action('chat'),'')]
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice), \
                 patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('intent_router.route',side_effect=decisions) as router:
                app=alice_desktop.Application(window)
                for text in ('Mon frere est Yanis','Oublie mon frere','Comment il s appelle ?','quitte'):
                    app.inputs.put(text)
                app.run()
            self.memory.forget_subject.assert_called_once_with('Oublie mon frere',app.confirm)
            recent=self.memory.answer.call_args_list[1].args[1]
            self.assertIn('SOURCE_REPLY',repr(recent))
            self.assertNotIn('Oublie mon frere',repr(recent))
            self.assertNotIn('Oubli annule',repr(recent))
            self.assertNotIn('Oublie mon frere',repr(router.call_args_list[-1]))
            voice.speak.assert_any_call('Oubli annule.')
        finally:window.destroy()

    def test_rejected_proposal_is_spoken_without_memory_or_action_execution(self):
        from action_policy import Action
        window=tk.Toplevel(self.root);window.withdraw()
        session,voice,hearing=Mock(model_spec={'name':'Modele validation'}),Mock(),Mock()
        try:
            with patch('alice_desktop.threading.Thread'), \
                 patch('alice_desktop.Session',return_value=session), \
                 patch('alice_desktop.Voice',return_value=voice), \
                 patch('alice_desktop.Hearing',return_value=hearing), \
                 patch('alice_desktop.pc_tools'), \
                 patch('alice_desktop.Actions') as actions, \
                 patch('intent_router.route',return_value=(Action('clarify'),'Precision necessaire.')):
                app=alice_desktop.Application(window)
                app.inputs.put('Demande fictive ambigue');app.inputs.put('quitte')
                app.run()
            self.memory.answer.assert_not_called()
            actions.return_value.execute.assert_not_called()
            voice.speak.assert_any_call('Precision necessaire.')
        finally:window.destroy()


if __name__ == '__main__':
    unittest.main()
