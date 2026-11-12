"""Isolated bridge checks: no game, microphone, memory or audio playback."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
VALIDATION = HERE.parents[1] / 'data' / 'validation'
VALIDATION.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))

import agent
from conversation_initiative import Proposal
from desktop_initiative import DesktopInitiative
from game_stream_bridge import BridgeClient, GameBridge, GameContext
from initiative_sequence import prepare


class FakeSession:
    def __init__(self):
        self.calls = []

    def check(self):
        pass

    def ask(self, messages, schema):
        self.calls.append((messages, schema))
        return json.dumps({'index': 1, 'reason': 'Je garde mes PV.'}), 0.1, {}


class BridgeTests(unittest.TestCase):
    def test_one_session_decides_and_reports_to_speaker(self):
        with tempfile.TemporaryDirectory(prefix='validation_sts_bridge_', dir=VALIDATION) as directory:
            state = Path(directory) / 'bridge.json'
            token = 'a' * 64
            context = GameContext()
            session = FakeSession()
            notices = []
            bridge = GameBridge(session, context, state, token,
                                on_notice=notices.append)
            bridge.start()
            try:
                client = BridgeClient(state, token)
                self.assertTrue(client.request('ping')['ok'])
                with patch.dict(os.environ, {'ALICE_STS_BRIDGE_FILE': str(state),
                                              'ALICE_STS_BRIDGE_TOKEN': token}):
                    advisor = agent.LocalAdvisor(agent.Learner(Path(directory) / 'learning.json'))
                    self.assertIsNone(advisor.session)
                    options = [{'kind': 'end', 'command': 'END'},
                               {'kind': 'play', 'command': 'PLAY 1 0',
                                'card': 'Strike_R', 'card_name': 'Strike',
                                'card_type': 'ATTACK', 'cost': 1, 'index': 1, 'target': 0}]
                    game = {'game_state': {'screen_type': 'NONE', 'floor': 1,
                             'combat_state': {'player': {'energy': 3},
                                 'hand': [{'id': 'Strike_R', 'name': 'Strike',
                                           'cost': 1, 'type': 'ATTACK',
                                           'is_playable': True}],
                                 'monsters': [{'name': 'Slime', 'current_hp': 10}]}}}
                    index, reason = advisor.choose(game, options)
                    self.assertEqual(index, 1)
                    self.assertEqual(reason, 'Je garde mes PV.')
                    self.assertIsNone(advisor.session)
                    advisor.report(options[index], 'model', reason,
                                   {'floor': 1, 'hp': 80, 'screen': 'NONE'},
                                   game['game_state'])
                    snapshot = context.snapshot()
                    self.assertEqual(snapshot['game'], 'Slay the Spire')
                    self.assertEqual(snapshot['recent_actions'][-1]['action'],
                                     'Strike sur Slime')
                    self.assertEqual(notices[-1]['reason'], reason)
                    self.assertEqual(len(session.calls), 2)
                    self.assertEqual(json.loads(session.calls[1][0][1]['content'])
                                     ['preliminary_choice_index'], 1)
                    advisor.close()
                self.assertIsNone(context.snapshot())
            finally:
                bridge.close()
            self.assertFalse(state.exists())

    def test_wrong_token_cannot_choose_or_inject_game_facts(self):
        with tempfile.TemporaryDirectory(prefix='validation_sts_bridge_', dir=VALIDATION) as directory:
            state = Path(directory) / 'bridge.json'
            context = GameContext()
            session = FakeSession()
            bridge = GameBridge(session, context, state, 'a' * 64)
            bridge.start()
            try:
                intruder = BridgeClient(state, 'b' * 64)
                with self.assertRaisesRegex(RuntimeError, 'refusee'):
                    intruder.event({'source': 'model', 'floor': 1, 'hp': 80,
                                    'action': 'faux choix', 'reason': 'faux'})
                self.assertEqual(session.calls, [])
                self.assertIsNone(context.snapshot())
            finally:
                bridge.close()

    def test_missing_bridge_does_not_start_a_second_model(self):
        with tempfile.TemporaryDirectory(prefix='validation_sts_bridge_', dir=VALIDATION) as directory:
            missing = Path(directory) / 'missing.json'
            with patch.dict(os.environ, {'ALICE_STS_BRIDGE_FILE': str(missing),
                                          'ALICE_STS_BRIDGE_TOKEN': 'a' * 64}):
                with self.assertRaises(FileNotFoundError):
                    agent.LocalAdvisor(agent.Learner(Path(directory) / 'learning.json'))

    def test_game_context_expires_and_prompt_distinguishes_intent(self):
        now = [10.0]
        context = GameContext(clock=lambda: now[0])
        context.record({'source': 'model', 'floor': 2, 'hp': 55,
                        'action': 'joue Bash', 'reason': 'Je veux affaiblir le monstre.',
                        'screen': 'NONE', 'enemies': ['Slime']})
        self.assertTrue(context.started.is_set())
        self.assertIn('Tu joues actuellement', context.prompt())
        self.assertIn('joue Bash', context.prompt())
        now[0] += 181
        self.assertIsNone(context.snapshot())
        self.assertEqual(context.prompt(), '')

    def test_animation_uses_game_facts_without_claiming_vision(self):
        schema = {'type': 'object', 'properties': {}}
        scene = [{'source': 'game', 'kind': 'status', 'text': 'joue Bash'}]
        messages, _ = prepare('Parle en francais.', schema, [], 'animation',
                              0, [], False, scene=scene)
        self.assertIn('Tu joues maintenant a Slay the Spire', messages[0]['content'])
        self.assertIn('Ne dis pas que tu vois l ecran', messages[0]['content'])
        self.assertIn('joue Bash', messages[1]['content'])

    def test_game_commentary_uses_voice_without_repeated_public_prompt(self):
        context = GameContext()
        context.record({'source': 'model', 'floor': 1, 'hp': 80,
                        'action': 'Strike sur Slime', 'reason': 'Je tente une attaque.'})
        confirmations = []
        spoken = []
        initiative = DesktopInitiative(FakeSession(),
            confirm=lambda text: confirmations.append(text) or True,
            game_context=context, auto_game_speech=True)
        try:
            initiative.set_mode('animation')
            initiative.idle([])
            with initiative.core.lock:
                initiative.core.ready = Proposal(
                    initiative.core.epoch, 'animation', 'topic',
                    'Je tente une attaque sur le Slime.')
            self.assertTrue(initiative.deliver(lambda text: spoken.append(text) or True,
                                                [], lambda: False))
            self.assertEqual(spoken, ['Je tente une attaque sur le Slime.'])
            self.assertEqual(confirmations, [])
            self.assertEqual(initiative.scene.snapshot()[-1]['source'], 'alice')
        finally:
            initiative.close()

    def test_game_speech_permission_ends_with_game_context(self):
        context = GameContext()
        confirmations = []
        initiative = DesktopInitiative(FakeSession(),
            confirm=lambda text: confirmations.append(text) or True,
            game_context=context, auto_game_speech=True)
        try:
            initiative.set_mode('animation')
            initiative.idle([])
            with initiative.core.lock:
                initiative.core.ready = Proposal(
                    initiative.core.epoch, 'animation', 'topic', 'Un autre sujet.')
            self.assertTrue(initiative.deliver(lambda text: True, [], lambda: False))
            self.assertEqual(len(confirmations), 1)
        finally:
            initiative.close()


if __name__ == '__main__':
    unittest.main()
