"""Protocol and adaptation checks with synthetic, isolated game data."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import agent
from experience import Experience, write_stream_status


class GameAgentTests(unittest.TestCase):
    @staticmethod
    def validation_directory():
        root = agent.LAB / "data" / "validation"
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="validation_sts_", dir=root)

    def test_only_playable_cards_and_live_targets_are_emitted(self):
        message = {
            "in_game": True, "available_commands": ["play", "end"],
            "game_state": {"combat_state": {
                "hand": [
                    {"id": "Strike_R", "type": "ATTACK", "is_playable": True, "has_target": True},
                    {"id": "Burn", "type": "STATUS", "is_playable": False, "has_target": False},
                    {"id": "Defend_R", "type": "SKILL", "is_playable": True, "has_target": False},
                ],
                "monsters": [{"current_hp": 12}, {"current_hp": 0}],
            }},
        }
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["PLAY 1 0", "PLAY 3", "END"])

    def test_learning_is_bounded_and_persists(self):
        with self.validation_directory() as temp:
            path = Path(temp) / "learning.json"
            learner = agent.Learner(path)
            for _ in range(10):
                learner.observe("Strike_R", 1000)
            self.assertGreater(learner.bonus("Strike_R"), 0)
            self.assertLessEqual(learner.bonus("Strike_R"), 2)
            learner.save()
            self.assertEqual(agent.Learner(path).values["Strike_R"]["count"], 10)

    def test_map_choices_are_read_from_game_state(self):
        message = {"in_game": True, "available_commands": ["choose"],
                   "game_state": {"screen_type": "MAP", "choice_list": ["x=0", "x=2"],
                                  "screen_state": {"next_nodes": [{"x": 0}, {"x": 2}]}}}
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["CHOOSE 0", "CHOOSE 1"])

    def test_full_potion_slots_do_not_offer_unresponsive_reward(self):
        message = {"in_game": True, "available_commands": ["choose", "proceed"],
                   "game_state": {"screen_type": "COMBAT_REWARD",
                                  "choice_list": ["gold", "potion"],
                                  "screen_state": {"rewards": [
                                      {"reward_type": "GOLD"}, {"reward_type": "POTION"}]},
                                  "potions": [{"name": "Ancient Potion", "id": "AncientPotion"},
                                              {"name": "Snecko Oil", "id": "SneckoOil"}]}}
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["CHOOSE 0", "PROCEED"])
        message["game_state"]["potions"][1] = {"name": "Potion Slot", "id": "Potion Slot"}
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["CHOOSE 0", "CHOOSE 1", "PROCEED"])

    def test_alice_can_choose_usable_potions_and_discard_for_a_reward(self):
        message = {"in_game": True, "available_commands": ["play", "end", "potion"],
                   "game_state": {"screen_type": "NONE", "potions": [
                       {"name": "Fire Potion", "can_use": True, "requires_target": True},
                       {"name": "Dexterity Potion", "can_use": True, "requires_target": False}],
                       "combat_state": {"monsters": [
                           {"name": "Slime", "current_hp": 12},
                           {"name": "Defeated", "current_hp": 0}]}}}
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["END", "POTION USE 0 0", "POTION USE 1"])
        message["game_state"]["screen_type"] = "HAND_SELECT"
        self.assertEqual([a["command"] for a in agent.candidates(message)], ["END"])
        message["available_commands"] = ["choose", "potion", "proceed"]
        message["game_state"].update({
            "screen_type": "COMBAT_REWARD", "combat_state": {},
            "choice_list": ["potion"],
            "screen_state": {"rewards": [{"reward_type": "POTION"}]},
            "potions": [{"name": "Fire Potion", "can_discard": True},
                        {"name": "Dexterity Potion", "can_discard": True}]})
        self.assertEqual([a["command"] for a in agent.candidates(message)],
                         ["POTION DISCARD 0", "POTION DISCARD 1", "PROCEED"])

    def test_transition_wait_is_bounded_action(self):
        message = {"in_game": True, "available_commands": ["wait", "state"],
                   "game_state": {"screen_type": "NONE"}}
        self.assertEqual([a["command"] for a in agent.candidates(message)], ["WAIT 30"])

    def test_shop_with_no_choices_uses_game_cancel_key(self):
        message = {"in_game": True, "available_commands": ["key", "click", "wait"],
                   "game_state": {"screen_type": "SHOP_SCREEN", "choice_list": []}}
        self.assertEqual([a["command"] for a in agent.candidates(message)], ["KEY Cancel 30"])

    def test_lethal_card_is_learned_at_combat_reward_transition(self):
        before = {"floor": 1, "turn": 1, "enemy_hp": 6, "block": 0, "hp": 70}
        after = {"floor": 1, "turn": 0, "enemy_hp": 0, "block": 0, "hp": 70}
        self.assertEqual(agent.observation_reward(before, after), 6)

    def test_selected_hand_card_can_be_confirmed(self):
        message = {"in_game": True, "available_commands": ["confirm", "wait"],
                   "game_state": {"screen_type": "HAND_SELECT",
                                  "screen_state": {"selected": [{"id": "Strike_R"}]}}}
        self.assertEqual([a["command"] for a in agent.candidates(message)], ["CONFIRM"])

    def test_personal_game_profile_is_rejected(self):
        with self.validation_directory() as temp:
            game = Path(temp) / "game"
            (game / "preferences").mkdir(parents=True)
            (game / "desktop-1.0.jar").touch()
            (game / "preferences" / "STSSaveSlots").write_text(
                json.dumps({"DEFAULT_SLOT": "0", "1_PROFILE_NAME": "validationAlice"}),
                encoding="utf-8")
            with patch.object(agent.Path, "cwd", return_value=game):
                with self.assertRaisesRegex(RuntimeError, "non actif"):
                    agent.run("policy", Path(temp) / "data")

    def test_complete_protocol_exchange_and_effect_observation(self):
        start = {"in_game": False, "available_commands": ["start"]}
        combat = {"in_game": True, "available_commands": ["play", "end"],
                  "game_state": {"floor": 1, "act": 1, "current_hp": 80,
                                 "combat_state": {"turn": 1, "player": {"block": 0},
                                                  "hand": [{"id": "Strike_R", "name": "Strike",
                                                            "type": "ATTACK", "cost": 1,
                                                            "is_playable": True, "has_target": True}],
                                                  "monsters": [{"current_hp": 20}]}}}
        after = {"in_game": True, "available_commands": ["end"],
                 "game_state": {"floor": 1, "act": 1, "current_hp": 80,
                                "combat_state": {"turn": 1, "player": {"block": 0},
                                                 "hand": [], "monsters": [{"current_hp": 14}]}}}
        end = {"in_game": False, "available_commands": []}
        transcript = io.StringIO("\n".join(json.dumps(item) for item in
                                           (start, combat, after, end)) + "\n")
        output = io.StringIO()
        with self.validation_directory() as temp:
            with patch.object(agent.sys, "stdin", transcript), redirect_stdout(output):
                agent.run("policy", Path(temp))
            self.assertEqual(output.getvalue().splitlines(),
                             ["ready", "START IRONCLAD 0", "PLAY 1 0", "END"])
            saved = json.loads((Path(temp) / "learning_policy.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["cards"]["Strike_R"]["estimate"], 6)

    def test_save_and_quit_does_not_count_as_completed_run(self):
        class Advisor:
            def __init__(self, learner, experience):
                pass

            def choose(self, message, actions, previous_card=None):
                return 0, ""

            def close(self):
                pass

        start = {"in_game": False, "available_commands": ["start"]}
        playing = {"in_game": True, "available_commands": ["wait"],
                   "game_state": {"floor": 1, "screen_type": "NONE"}}
        menu = {"in_game": False, "available_commands": []}
        with self.validation_directory() as temp:
            transcript = io.StringIO("\n".join(json.dumps(row) for row in
                                             (start, playing, menu)) + "\n")
            with patch.object(agent, "LocalAdvisor", Advisor), \
                 patch.object(agent.sys, "stdin", transcript), redirect_stdout(io.StringIO()):
                agent.run("alice", Path(temp))
            self.assertEqual(Experience(Path(temp) / "experience.json").runs, [])
            log = next(Path(temp).glob("validation_run_*.jsonl"))
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[-1]["summary"]["termination"], "player_exit")

    def test_witnessed_defeat_counts_as_completed_run(self):
        class Advisor:
            def __init__(self, learner, experience):
                pass

            def choose(self, message, actions, previous_card=None):
                return 0, ""

            def close(self):
                pass

        start = {"in_game": False, "available_commands": ["start"]}
        defeat = {"in_game": True, "available_commands": ["proceed"],
                  "game_state": {"floor": 3, "screen_type": "GAME_OVER"}}
        menu = {"in_game": False, "available_commands": []}
        with self.validation_directory() as temp:
            transcript = io.StringIO("\n".join(json.dumps(row) for row in
                                             (start, defeat, menu)) + "\n")
            with patch.object(agent, "LocalAdvisor", Advisor), \
                 patch.object(agent.sys, "stdin", transcript), redirect_stdout(io.StringIO()):
                agent.run("alice", Path(temp))
            self.assertEqual(Experience(Path(temp) / "experience.json").runs,
                             [{"floor": 3, "result": "defaite"}])

    def test_alice_decides_combat_order_instead_of_policy(self):
        class Advisor:
            def __init__(self, learner, experience):
                pass

            def choose(self, message, actions, previous_card=None):
                if len(actions) == 1:
                    return 0, "seule action possible"
                return (next(i for i, item in enumerate(actions)
                             if item["kind"] == "end"), "Alice")

            def close(self):
                pass

        start = {"in_game": False, "available_commands": ["start"]}
        combat = {"in_game": True, "available_commands": ["play", "end"],
                  "game_state": {"floor": 1, "combat_state": {
                      "hand": [{"id": "Strike_R", "name": "Strike", "type": "ATTACK",
                                "cost": 1, "is_playable": True, "has_target": True}],
                      "monsters": [{"current_hp": 20}]}}}
        end = {"in_game": False, "available_commands": []}
        transcript = io.StringIO("\n".join(json.dumps(row) for row in
                                           (start, combat, end)) + "\n")
        output = io.StringIO()
        with self.validation_directory() as temp:
            with patch.object(agent, "LocalAdvisor", Advisor), \
                 patch.object(agent.sys, "stdin", transcript), \
                 patch.object(agent.time, "sleep") as pause, redirect_stdout(output):
                agent.run("alice", Path(temp), decision_pace=2.0)
            self.assertEqual(output.getvalue().splitlines(),
                             ["ready", "START IRONCLAD 0", "END"])
            log = next(Path(temp).glob("validation_run_*.jsonl"))
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[1]["source"], "model")
            self.assertEqual(rows[1]["decision"]["options"][0]["command"], "PLAY 1 0")
            self.assertEqual(rows[1]["decision"]["paced_to_ms"], 2000)
            self.assertEqual(rows[1]["action"], "END")
            self.assertIn("command_sent_at", rows[1])
            self.assertGreaterEqual(rows[1]["delay_to_send_ms"], 0)
            pause.assert_called_once_with(2.0)

    def test_alice_stops_if_model_cannot_choose(self):
        class Advisor:
            def __init__(self, learner, experience):
                pass

            def choose(self, message, actions, previous_card=None):
                if len(actions) > 1:
                    raise RuntimeError("test model failure")
                return 0, "seule action possible"

            def close(self):
                pass

        start = {"in_game": False, "available_commands": ["start"]}
        combat = {"in_game": True, "available_commands": ["play", "end"],
                  "game_state": {"combat_state": {
                      "hand": [{"id": "Strike_R", "is_playable": True,
                                "has_target": True}],
                      "monsters": [{"current_hp": 20}]}}}
        transcript = io.StringIO("\n".join(json.dumps(row) for row in
                                           (start, combat)) + "\n")
        output = io.StringIO()
        with self.validation_directory() as temp:
            with patch.object(agent, "LocalAdvisor", Advisor), \
                 patch.object(agent.sys, "stdin", transcript), redirect_stdout(output):
                agent.run("alice", Path(temp))
            self.assertEqual(output.getvalue().splitlines(), ["ready", "START IRONCLAD 0"])
            log = next(Path(temp).glob("validation_run_*.jsonl"))
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[-1]["summary"]["termination"], "model_unavailable")

    def test_visible_combat_experience_survives_restart_and_reaches_alice_prompt(self):
        with self.validation_directory() as temp:
            root = Path(temp)
            memory = Experience(root / "experience.json")
            memory.observe_pair("Flex", "Strike_R", 9)
            memory.observe_pair("Flex", "Strike_R", 11)
            memory.record_fight({"act": 1, "floor": 3, "enemies": ["Slime"],
                                 "start_hp": 70, "lowest_hp": 60, "turns": 2,
                                 "cards": ["Flex", "Strike_R"]}, 64, True)
            memory.record_run(3, "defaite")
            recovered = Experience(root / "experience.json")
            self.assertEqual(recovered.pair_context("Flex", [{"id": "Strike_R"}])[0]["samples"], 2)
            self.assertEqual(recovered.similar_fights(["Slime"])[0]["hp_lost"], 10)
            advisor = agent.LocalAdvisor(agent.Learner(root / "learning.json"), recovered)
            message = {"in_game": True, "available_commands": ["play", "end"],
                       "game_state": {"floor": 4, "combat_state": {
                           "turn": 1, "player": {"energy": 2},
                           "hand": [{"id": "Strike_R", "name": "Strike", "cost": 1,
                                     "is_playable": True, "has_target": True}],
                           "monsters": [{"name": "Slime", "current_hp": 20}]}}}
            prompt = json.loads(advisor._prompt(message, agent.candidates(message), "Flex"))
            self.assertEqual(prompt["state"]["observed_sequences"][0]["after"], "Flex")
            self.assertEqual(prompt["state"]["previous_fights"][0]["turns"], 2)
            status = root / "stream_status.txt"
            write_stream_status(status, run_number=2, state={"floor": 4, "hp": 64},
                                action="Strike sur Slime", source="model", reason="pour finir le combat",
                                experience=recovered)
            text = status.read_text(encoding="utf-8")
            self.assertIn("Strike sur Slime", text)
            self.assertIn("Experience : 1 combats", text)
            write_stream_status(status, run_number=2, state={"floor": 4, "hp": 64},
                                action="continuer", source="forced",
                                last_alice_action="Strike sur Slime",
                                last_alice_reason="pour finir le combat")
            text = status.read_text(encoding="utf-8")
            self.assertIn("automatique (option unique)", text)
            self.assertIn("Dernier choix d'Alice : Strike sur Slime", text)

    def test_model_call_keeps_raw_answer_and_latency_for_audit(self):
        class Session:
            def __init__(self):
                self.calls = []

            def ask(self, messages, schema):
                self.calls.append(messages)
                if len(self.calls) == 1:
                    return '{"index":0,"reason":"choix provisoire"}', None, None
                return '{"index":1,"reason":"je bloque les degats"}', None, None

            def close(self):
                pass

        with self.validation_directory() as temp:
            advisor = agent.LocalAdvisor(agent.Learner(Path(temp) / "learn.json"))
            session = Session()
            advisor.session = session
            message = {"in_game": True, "available_commands": ["play", "end"],
                       "game_state": {"screen_type": "NONE", "combat_state": {
                           "hand": [{"id": "Defend_R", "name": "Defend", "cost": 1,
                                     "is_playable": True, "has_target": False}],
                           "monsters": [{"name": "Slime", "current_hp": 12}]}}}
            options = agent.candidates(message)
            index, reason = advisor.choose(message, options)
            self.assertEqual(index, 1)
            self.assertEqual(reason, "je bloque les degats")
            self.assertTrue(advisor.last_decision["model_called"])
            self.assertTrue(advisor.last_decision["reviewed"])
            self.assertEqual(advisor.last_decision["preliminary_index"], 0)
            self.assertEqual(len(session.calls), 2)
            self.assertEqual(json.loads(session.calls[1][1]["content"])
                             ["preliminary_choice_index"], 0)
            self.assertIn('"index":1', advisor.last_decision["raw_response"])
            self.assertGreaterEqual(advisor.last_decision["decision_ms"], 0)

    def test_review_failure_stops_without_executing_draft_choice(self):
        class Session:
            def __init__(self):
                self.calls = 0

            def ask(self, messages, schema):
                self.calls += 1
                if self.calls == 1:
                    return '{"index":0}', None, None
                raise RuntimeError("review unavailable")

            def close(self):
                pass

        with self.validation_directory() as temp:
            advisor = agent.LocalAdvisor(agent.Learner(Path(temp) / "learn.json"))
            session = Session()
            advisor.session = session
            message = {"in_game": True, "available_commands": ["play", "end"],
                       "game_state": {"screen_type": "NONE", "combat_state": {
                           "hand": [{"id": "Strike_R", "name": "Strike", "cost": 1,
                                     "is_playable": True, "has_target": False}],
                           "monsters": [{"name": "Slime", "current_hp": 12}]}}}
            with self.assertRaisesRegex(RuntimeError, "review unavailable"):
                advisor.choose(message, agent.candidates(message))
            self.assertEqual(session.calls, 2)
            self.assertEqual(advisor.last_decision["preliminary_index"], 0)
            self.assertIn("error", advisor.last_decision)

    def test_card_reward_options_include_real_card_description(self):
        with self.validation_directory() as temp:
            advisor = agent.LocalAdvisor(agent.Learner(Path(temp) / "learn.json"))
            advisor.card_text_by_name = {"pummel": "Deal !D! damage !M! times. Exhaust."}
            message = {"in_game": True, "available_commands": ["choose"],
                       "game_state": {"screen_type": "CARD_REWARD",
                                      "choice_list": ["Pummel", "Skip"]}}
            prompt = json.loads(advisor._prompt(message, agent.candidates(message)))
            self.assertEqual(prompt["options"][0]["effect_text"],
                             "Deal !D! damage !M! times. Exhaust.")


if __name__ == "__main__":
    unittest.main()
