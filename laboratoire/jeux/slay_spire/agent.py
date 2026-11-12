"""Bridge between CommunicationMod and Alice's local game decisions.

Only protocol commands go to the game. Standard output is reserved for them.
This module never sends keyboard input to Windows or reads Alice's memory.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from experience import Experience, write_stream_status


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
DATA = LAB / "data" / "slay_spire"
MAX_RUN_ACTIONS = 5000


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def candidates(message):
    """Return commands justified by the mod's current action list and state."""
    allowed = {str(x).lower() for x in message.get("available_commands", [])}
    state = message.get("game_state") or {}
    result = []
    if not message.get("in_game"):
        if "start" in allowed:
            return [{"command": "START IRONCLAD 0", "kind": "start"}]
        return result

    combat = state.get("combat_state") or {}
    monsters = combat.get("monsters") or []
    targets = [i for i, monster in enumerate(monsters)
               if not monster.get("is_gone") and not monster.get("half_dead")
               and number(monster.get("current_hp")) > 0]
    if "play" in allowed:
        for index, card in enumerate(combat.get("hand") or [], 1):
            if not card.get("is_playable"):
                continue
            base = {"kind": "play", "card": card.get("id") or card.get("name") or "unknown",
                    "card_name": card.get("name") or "unknown", "card_type": card.get("type") or "",
                    "cost": number(card.get("cost")), "index": index}
            if card.get("has_target"):
                for target in targets:
                    result.append({**base, "command": f"PLAY {index} {target}", "target": target})
            else:
                result.append({**base, "command": f"PLAY {index}"})
    if "end" in allowed:
        result.append({"command": "END", "kind": "end"})

    potions = state.get("potions") or []
    rewards = (state.get("screen_state") or {}).get("rewards") or []
    potion_reward = (state.get("screen_type") == "COMBAT_REWARD" and any(
        reward.get("reward_type") == "POTION" for reward in rewards))
    potion_full = bool(potions) and all(
        p.get("name") != "Potion Slot" and p.get("id") not in ("Potion Slot", "PotionSlot")
        for p in potions)
    if "potion" in allowed:
        for slot, potion in enumerate(potions):
            label = str(potion.get("name") or "potion")
            if potion.get("can_use") and combat and state.get("screen_type") == "NONE":
                if potion.get("requires_target"):
                    for target in targets:
                        result.append({"command": f"POTION USE {slot} {target}",
                                       "kind": "potion_use", "potion": label,
                                       "slot": slot, "target": target})
                else:
                    result.append({"command": f"POTION USE {slot}",
                                   "kind": "potion_use", "potion": label, "slot": slot})
            if potion_reward and potion_full and potion.get("can_discard"):
                result.append({"command": f"POTION DISCARD {slot}",
                               "kind": "potion_discard", "potion": label, "slot": slot})

    if "choose" in allowed:
        for index, choice in enumerate(state.get("choice_list") or []):
            reward = rewards[index] if index < len(rewards) else {}
            if (state.get("screen_type") == "COMBAT_REWARD" and potion_full and
                    (reward.get("reward_type") == "POTION" or str(choice).lower() == "potion")):
                # CommunicationMod does not reply after taking a potion with full slots.
                continue
            result.append({"command": f"CHOOSE {index}", "kind": "choose",
                           "choice": str(choice)[:160], "index": index})
    if "proceed" in allowed or "confirm" in allowed:
        command = "PROCEED" if "proceed" in allowed else "CONFIRM"
        result.append({"command": command, "kind": "proceed"})
    if "return" in allowed and not result:
        result.append({"command": "RETURN", "kind": "return"})
    if state.get("screen_type") == "SHOP_SCREEN" and "key" in allowed and not result:
        # Some shop states expose no RETURN or affordable choices to the mod.
        result.append({"command": "KEY Cancel 30", "kind": "shop_leave"})
    if "wait" in allowed and not result:
        result.append({"command": "WAIT 30", "kind": "wait"})
    return result


def incoming_damage(state):
    combat = state.get("combat_state") or {}
    total = 0.0
    for monster in combat.get("monsters") or []:
        if monster.get("is_gone") or monster.get("half_dead"):
            continue
        intent = str(monster.get("intent") or "").upper()
        if "ATTACK" in intent:
            hits = max(1, number(monster.get("move_hits"), 1))
            damage = number(monster.get("move_adjusted_damage"), -1)
            if damage < 0:
                damage = number(monster.get("move_base_damage"))
            total += max(0, damage) * hits
    return total


class Learner:
    """Small bounded online estimate of observed card effects, per game profile."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.values = raw.get("cards", {}) if raw.get("version") == 1 else {}
        except (OSError, ValueError, TypeError):
            self.values = {}

    def bonus(self, card):
        item = self.values.get(card) or {}
        count = max(0, int(number(item.get("count"))))
        estimate = number(item.get("estimate"))
        return max(-2.0, min(2.0, estimate / 6.0)) * min(1.0, count / 5.0)

    def observe(self, card, reward):
        if not card:
            return
        item = self.values.get(card) or {"count": 0, "estimate": 0.0}
        count = max(0, int(number(item.get("count")))) + 1
        estimate = number(item.get("estimate"))
        # Bounded moving average; recent observations can correct old estimates.
        rate = 1.0 if count == 1 else min(0.2, 1.0 / count)
        estimate += rate * (max(-20, min(20, reward)) - estimate)
        self.values[card] = {"count": count, "estimate": round(estimate, 4)}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": 1, "cards": self.values},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)


def score(action, message, learner):
    state = message.get("game_state") or {}
    if action["kind"] == "start":
        return 100.0
    if action["kind"] == "play":
        card = action["card"]
        card_type = str(action["card_type"]).upper()
        incoming = max(0, incoming_damage(state) - number((state.get("combat_state") or {}).get("player", {}).get("block")))
        base = 9.0 if card_type == "ATTACK" else 7.0
        if card_type == "SKILL" and incoming > 0:
            base += min(5.0, incoming / 3.0)
        if card_type == "POWER":
            base += 3.0
        if card.lower().startswith("defend") and incoming <= 0:
            base -= 8.0
        if card.lower().startswith("bash"):
            base += 2.0
        base -= max(0, action["cost"] - 1) * 0.3
        monsters = (state.get("combat_state") or {}).get("monsters") or []
        if "target" in action and action["target"] < len(monsters):
            target = monsters[action["target"]]
            # Prefer a weak target, with a small bias so it cannot override card value.
            base += 0.7 / (1 + max(0, number(target.get("current_hp"))) / 20)
        return base + learner.bonus(card)
    if action["kind"] == "end":
        return 0.0
    if action["kind"] == "choose":
        choice = action["choice"].lower()
        screen = str(state.get("screen_type") or state.get("screen_name") or "").upper()
        if "CARD_REWARD" in screen:
            if "skip" in choice:
                return -2.0
            return 1.0
        if "MAP" in screen:
            return 1.0
        if "REST" in screen and "rest" in choice:
            hp = number(state.get("current_hp"))
            max_hp = max(1, number(state.get("max_hp"), 1))
            return 4.0 if hp / max_hp < 0.65 else 0.0
        return 2.0
    if action["kind"] == "proceed":
        return 1.0
    if action["kind"] == "wait":
        return -2.0
    return -1.0


def progress(state):
    combat = state.get("combat_state") or {}
    monsters = combat.get("monsters") or []
    player = combat.get("player") or {}
    return {
        "floor": int(number(state.get("floor"))),
        "act": int(number(state.get("act"))),
        "hp": number(state.get("current_hp"), number(player.get("current_hp"))),
        "block": number(player.get("block")),
        "enemy_hp": sum(max(0, number(m.get("current_hp"))) for m in monsters
                        if not m.get("is_gone")),
        "turn": int(number(combat.get("turn"))),
        "screen": str(state.get("screen_type") or state.get("screen_name") or ""),
    }


def observation_reward(before, after):
    # Immediate, visible effects only. We never interpret this as a win rate.
    if before["floor"] != after["floor"]:
        return 0.0
    damage = max(0, before["enemy_hp"] - after["enemy_hp"])
    # Block disappears at turn boundaries, so only compare it within a turn.
    protection = (max(0, after["block"] - before["block"])
                  if before["turn"] == after["turn"] else 0)
    injury = max(0, before["hp"] - after["hp"])
    return damage + min(15, protection) * 0.5 - injury * 1.5


class LocalAdvisor:
    """Alice chooses every non-trivial action; Python executes the legal choice."""

    def __init__(self, learner, experience=None):
        self.session = None
        sys.path.insert(0, str(LAB / "scripts"))
        from game_stream_bridge import client_from_environment
        self.bridge = client_from_environment()
        if self.bridge is not None:
            self.bridge.request('ping')
        self.closed = False
        self.learner = learner
        self.experience = experience
        self.last_context = {"sequences": 0, "fights": 0}
        self.last_decision = {}
        self.card_text = {}
        self.card_text_by_name = {}
        game_jar = Path.cwd() / "desktop-1.0.jar"
        if game_jar.exists():
            try:
                with zipfile.ZipFile(game_jar) as archive:
                    cards = json.loads(archive.read("localization/eng/cards.json"))
                self.card_text = {key: str(value.get("DESCRIPTION", "")).replace(" NL ", " ")[:180]
                                  for key, value in cards.items() if isinstance(value, dict)}
                self.card_text_by_name = {str(value.get("NAME", "")).casefold():
                                          str(value.get("DESCRIPTION", "")).replace(" NL ", " ")[:180]
                                          for value in cards.values() if isinstance(value, dict)
                                          and value.get("NAME")}
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                pass

    def _prompt(self, message, actions, previous_card=None):
        self.last_context = {"sequences": 0, "fights": 0}
        state = message.get("game_state") or {}
        combat = state.get("combat_state") or {}
        player = combat.get("player") or {}
        monsters = combat.get("monsters") or []
        summary = {key: state.get(key) for key in
                   ("screen_type", "floor", "act", "current_hp", "max_hp", "gold")}
        summary["potions"] = [{"slot": i, "name": potion.get("name")}
                              for i, potion in enumerate(state.get("potions") or [])
                              if potion.get("name") != "Potion Slot"]
        if combat:
            summary["energy"] = player.get("energy")
            summary["block"] = player.get("block")
            summary["incoming_damage"] = incoming_damage(state)
            summary["enemies"] = [{"index": i, "name": m.get("name"),
                                   "hp": m.get("current_hp"), "block": m.get("block"),
                                   "intent": m.get("intent"),
                                   "attack_damage": m.get("move_adjusted_damage"),
                                   "attack_hits": m.get("move_hits")}
                                  for i, m in enumerate(monsters) if not m.get("is_gone")]
            if self.experience:
                summary["previous_card_this_turn"] = previous_card
                summary["observed_sequences"] = self.experience.pair_context(
                    previous_card, combat.get("hand") or [])
                summary["previous_fights"] = self.experience.similar_fights(
                    [m.get("name") for m in monsters if m.get("name")])
                self.last_context = {"sequences": len(summary["observed_sequences"]),
                                     "fights": len(summary["previous_fights"])}
            summary["hand"] = []
            for index, card in enumerate(combat.get("hand") or [], 1):
                card_id = card.get("id") or ""
                item = {"index": index, "name": card.get("name"),
                        "cost": card.get("cost"), "type": card.get("type"),
                        "playable": card.get("is_playable"),
                        "effect_text": self.card_text.get(card_id, "")}
                learned = self.learner.values.get(card_id) or {}
                if learned.get("count"):
                    item["observed_impact"] = learned.get("estimate")
                    item["observations"] = learned.get("count")
                summary["hand"].append(item)
        else:
            summary["screen_state"] = json.dumps(state.get("screen_state") or {},
                                                 ensure_ascii=False)[:1200]
        options = []
        for index, action in enumerate(actions):
            option = {"index": index, "kind": action["kind"]}
            if action["kind"] == "play":
                option.update({"card_index": action["index"],
                               "target": action.get("target")})
            elif action["kind"].startswith("potion_"):
                option.update({"potion": action["potion"], "slot": action["slot"],
                               "target": action.get("target")})
            elif action["kind"] == "choose":
                option["choice"] = action["choice"]
                if state.get("screen_type") == "CARD_REWARD":
                    option["effect_text"] = self.card_text_by_name.get(
                        action["choice"].casefold(), "")
            options.append(option)
        return json.dumps({"state": summary, "options": options}, ensure_ascii=False)

    def choose(self, message, actions, previous_card=None):
        if len(actions) < 2:
            self.last_decision = {"raw_response": None, "decision_ms": 0,
                                  "model_called": False}
            return 0, "seule action possible"
        started_at = time.perf_counter()
        raw_response = None
        first_index = None
        try:
            if self.session is None and self.bridge is None:
                from chat import Session
                self.session = Session(allow_game=True, fps_protection=True,
                                       ram_protection=True, context_window=4096)
                self.session.start()
            prompt = self._prompt(message, actions, previous_card)
            schema = {"type": "object", "properties": {"index": {"type": "integer"},
                                                       "reason": {"type": "string"}},
                      "required": ["index"]}
            instructions = ("Tu es Alice, la joueuse de Slay the Spire. Chaque option est une action legale que ton interface executera pour toi. Choisis toi-meme la prochaine carte, la cible, la potion ou la fin du tour selon la situation. Garde les potions utiles pour les combats difficiles, mais utilise-les si elles evitent une perte de PV importante ou une defaite. Preserve tes PV, cherche la victoire. Les textes !D!, !B! et !M! sont des valeurs variables. observed_impact, observed_sequences et previous_fights sont des observations de vraies parties, pas des preuves qu'un choix cause le resultat. Utilise-les prudemment. Reponds en JSON avec index exact et reason, une phrase tres courte en francais pour le stream.")

            def request_choice(system, user):
                nonlocal raw_response
                messages = [{"role": "system", "content": system},
                            {"role": "user", "content": user}]
                if self.bridge is not None:
                    response = self.bridge.decide(messages, schema)
                else:
                    response, _, _ = self.session.ask(messages, schema)
                raw_response = response
                answer = json.loads(response)
                index = answer.get("index")
                if type(index) is not int or not 0 <= index < len(actions):
                    raise ValueError("index de choix invalide")
                return index, str(answer.get("reason") or "")[:120], response

            first_index, _, _ = request_choice(instructions, prompt)
            review = json.loads(prompt)
            review["preliminary_choice_index"] = first_index
            review_instructions = (instructions + " Reexamine le choix provisoire avant de jouer. Compare-le aux autres options legales : degats entrants, bloc, energie, possibilite de finir le combat, ressources depensees et cartes encore en main. Anticipe au moins la prochaine action possible, sans inventer les cartes de la pioche ni le resultat d'une commande. Les degats exacts d'une carte ne sont pas toujours fournis : ne presente pas une victoire comme certaine sans chiffres suffisants. Si le choix provisoire reste le meilleur, conserve son index ; sinon corrige-le. Donne seulement ton choix final et sa raison courte.")
            index, reason, raw_response = request_choice(
                review_instructions, json.dumps(review, ensure_ascii=False))
            self.last_decision = {"raw_response": raw_response[:1000],
                                  "decision_ms": round((time.perf_counter() - started_at) * 1000),
                                  "model_called": True, "reviewed": True,
                                  "preliminary_index": first_index}
            return index, reason
        except Exception as error:
            self.last_decision = {"raw_response": str(raw_response)[:1000],
                                  "decision_ms": round((time.perf_counter() - started_at) * 1000),
                                  "model_called": True, "reviewed": False,
                                  "preliminary_index": first_index,
                                  "error": str(error)[:300]}
            self.close()
            raise RuntimeError(f"Alice ne peut pas choisir: {type(error).__name__}: {error}") from error

    def close(self):
        if not self.closed and self.bridge is not None:
            try:
                self.bridge.finish()
            except (OSError, ValueError, RuntimeError):
                pass
        self.closed = True
        if self.session is not None:
            self.session.close()
            self.session = None

    def report(self, action, source, reason, current, state):
        if self.bridge is None:
            return
        monsters = (state.get('combat_state') or {}).get('monsters') or []
        self.bridge.event({'source': source, 'floor': int(current['floor']),
                           'hp': current['hp'], 'screen': str(current.get('screen') or ''),
                           'action': display_action(action, state), 'reason': reason,
                           'enemies': [str(m.get('name')) for m in monsters
                                       if isinstance(m, dict) and m.get('name')
                                       and not m.get('is_gone')][:3]})


def display_action(action, state):
    if action["kind"] == "potion_use":
        return "utilise " + action["potion"]
    if action["kind"] == "potion_discard":
        return "jette " + action["potion"]
    if action["kind"] == "play":
        label = str(action.get("card_name") or action.get("card") or "carte")
        target = action.get("target")
        monsters = (state.get("combat_state") or {}).get("monsters") or []
        if isinstance(target, int) and target < len(monsters):
            label += " sur " + str(monsters[target].get("name") or "ennemi")
        return label
    if action["kind"] == "choose":
        return str(action.get("choice") or "choix")
    if action["kind"] == "end":
        return "fin du tour"
    return action["command"]


def run(mode, data_dir, max_actions=MAX_RUN_ACTIONS, decision_pace=0.0):
    game_dir = Path.cwd()
    slots_path = game_dir / "preferences" / "STSSaveSlots" if (game_dir / "desktop-1.0.jar").exists() else None

    def profile_is_safe():
        if slots_path is None:
            return True
        try:
            slots = json.loads(slots_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError("Profil du jeu impossible a verifier") from error
        return str(slots.get("DEFAULT_SLOT")) == "1" and slots.get("1_PROFILE_NAME") == "validationAlice"

    if not profile_is_safe():
        raise RuntimeError("Profil validationAlice non actif; agent refuse de jouer")
    data_dir.mkdir(parents=True, exist_ok=True)
    learner = Learner(data_dir / ("learning.json" if mode == "alice" else "learning_policy.json"))
    experience = Experience(data_dir / "experience.json") if mode == "alice" else None
    advisor = LocalAdvisor(learner, experience) if mode == "alice" else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = data_dir / f"validation_run_{stamp}_{os.getpid()}.jsonl"
    started = False
    prior = None
    errors = 0
    best_floor = 0
    actions_done = 0
    consecutive_waits = 0
    termination = "input_closed"
    active_fight = None
    last_fight = None
    last_card = None
    last_turn = None
    last_display = ""
    last_reason = ""
    last_source = ""
    last_alice_action = ""
    last_alice_reason = ""
    last_matches = 0
    last_decision_ms = 0
    last_option_count = 0
    last_state = {"floor": 0, "hp": 0}
    result_marker = "fin"
    run_number = len(experience.runs) + 1 if experience else 0
    status_path = data_dir / "stream_status.txt"
    if experience:
        write_stream_status(status_path, run_number=run_number, state=last_state,
                            experience=experience)
    print("ready", flush=True)
    try:
        with log_path.open("a", encoding="utf-8") as log:
            for line in sys.stdin:
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("expected a JSON object")
                    if message.get("error"):
                        errors += 1
                        log.write(json.dumps({"error": str(message["error"])[:300]}, ensure_ascii=False) + "\n")
                        log.flush()
                        if errors >= 3:
                            termination = "protocol_errors"
                            break
                    else:
                        errors = 0
                    state = message.get("game_state") or {}
                    current = progress(state)
                    if message.get("in_game") or not started:
                        last_state = current
                    best_floor = max(best_floor, current["floor"])
                    turn_key = (current["act"], current["floor"], current["turn"])
                    if turn_key != last_turn:
                        last_card = None
                        last_turn = turn_key
                    if prior and prior["action"]["kind"] == "play":
                        impact = observation_reward(prior["state"], current)
                        learner.observe(prior["action"]["card"], impact)
                        learner.save()
                        if (experience and prior.get("previous_card") and
                                prior["state"]["floor"] == current["floor"] and
                                prior["state"]["turn"] == current["turn"]):
                            experience.observe_pair(prior["previous_card"],
                                                    prior["action"]["card"], impact)
                    prior = None
                    if experience:
                        if active_fight and current["screen"] in ("COMBAT_REWARD", "GAME_OVER"):
                            last_fight = experience.record_fight(
                                active_fight, current["hp"], current["screen"] == "COMBAT_REWARD")
                            active_fight = None
                        if current["screen"] == "GAME_OVER":
                            result_marker = "defaite"
                        elif current["screen"] in ("VICTORY", "TRUE_VICTORY"):
                            result_marker = "victoire"
                        combat = state.get("combat_state") or {}
                        if (message.get("in_game") and current["screen"] == "NONE"
                                and combat.get("monsters")):
                            fight_key = (current["act"], current["floor"])
                            if active_fight is None or active_fight["key"] != fight_key:
                                active_fight = {"key": fight_key, "act": current["act"],
                                                "floor": current["floor"], "start_hp": current["hp"],
                                                "lowest_hp": current["hp"],
                                                "turns": 0, "enemies": [], "cards": []}
                            active_fight["lowest_hp"] = min(active_fight["lowest_hp"], current["hp"])
                            active_fight["turns"] = max(active_fight["turns"], current["turn"])
                            active_fight["enemies"].extend(
                                str(m.get("name")) for m in combat["monsters"] if m.get("name"))
                    if started and not message.get("in_game"):
                        # Save & Quit also returns to the menu. Only a witnessed
                        # victory or defeat is a completed run for progress stats.
                        termination = "game_ended" if result_marker != "fin" else "player_exit"
                        if experience and termination == "game_ended":
                            experience.record_run(best_floor, result_marker)
                        break
                    if actions_done >= max_actions:
                        termination = "action_limit"
                        break
                    if not profile_is_safe():
                        termination = "profile_changed"
                        break
                    options = candidates(message)
                    if not options:
                        # Unsupported screen: return control to the human instead of guessing clicks.
                        log.write(json.dumps({"unsupported": current}, ensure_ascii=False) + "\n")
                        log.flush()
                        termination = "unsupported_screen"
                        break
                    if advisor:
                        try:
                            choice, reason = advisor.choose(message, options, last_card)
                        except RuntimeError as error:
                            log.write(json.dumps({"model_error": str(error)[:300]}, ensure_ascii=False) + "\n")
                            log.flush()
                            termination = "model_unavailable"
                            break
                        source = "model" if len(options) > 1 else "forced"
                    else:
                        choice = max(range(len(options)), key=lambda i: score(options[i], message, learner))
                        source = "policy"
                        reason = ""
                    action = options[choice]
                    decision = getattr(advisor, "last_decision", {}) if advisor else {}
                    option_labels = [{"index": i, "action": display_action(option, state),
                                      "command": option["command"]}
                                     for i, option in enumerate(options)]
                    consecutive_waits = consecutive_waits + 1 if action["kind"] == "wait" else 0
                    if consecutive_waits > 20:
                        log.write(json.dumps({"stalled": current}, ensure_ascii=False) + "\n")
                        termination = "stalled"
                        break
                    if action["kind"] == "start":
                        started = True
                    record = {"time": datetime.now(timezone.utc).isoformat(),
                              "mode": mode, "state": current, "action": action["command"],
                              "card": action.get("card"), "choice": action.get("choice"),
                              "source": source, "reason": reason if source == "model" else "",
                              "decision": {"options": option_labels, "chosen_index": choice,
                                           "model_called": source == "model",
                                           "decision_ms": decision.get("decision_ms", 0),
                                           "reviewed": decision.get("reviewed", False),
                                           "preliminary_index": decision.get("preliminary_index"),
                                           "paced_to_ms": round(decision_pace * 1000) if source == "model" else 0,
                                           "raw_response": decision.get("raw_response")},
                              "experience_presented": getattr(advisor, "last_context", {})
                              if source == "model" else {}}
                    if action["kind"] == "play":
                        prior = {"state": current, "action": action,
                                 "previous_card": last_card}
                        last_card = action["card"]
                        if active_fight and len(active_fight["cards"]) < 30:
                            active_fight["cards"].append(action["card"])
                    if experience:
                        last_display = display_action(action, state)
                        last_reason = reason if source == "model" else ""
                        last_source = source
                        last_option_count = len(options)
                        last_decision_ms = decision.get("decision_ms", 0)
                        last_matches = 0
                        if source == "model":
                            last_alice_action = last_display
                            last_alice_reason = last_reason
                            context = getattr(advisor, "last_context", {})
                            last_matches = context.get("sequences", 0) + context.get("fights", 0)
                        write_stream_status(status_path, run_number=run_number,
                                            state=current, action=last_display,
                                            source=source,
                                            reason=last_reason, experience=experience,
                                            last_fight=last_fight, memory_matches=last_matches,
                                            decision_ms=last_decision_ms,
                                            option_count=last_option_count,
                                            last_alice_action=last_alice_action,
                                            last_alice_reason=last_alice_reason)
                    if source == "model" and decision_pace > 0:
                        time.sleep(max(0.0, decision_pace - decision.get("decision_ms", 0) / 1000.0))
                    print(action["command"], flush=True)
                    sent_at = datetime.now(timezone.utc)
                    record["command_sent_at"] = sent_at.isoformat()
                    record["delay_to_send_ms"] = round(
                        (sent_at - datetime.fromisoformat(record["time"])).total_seconds() * 1000)
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log.flush()
                    actions_done += 1
                    if advisor and getattr(advisor, 'bridge', None) is not None:
                        try:
                            advisor.report(action, source, reason, current, state)
                        except (OSError, ValueError, RuntimeError) as error:
                            log.write(json.dumps({"bridge_error": str(error)[:300]},
                                                 ensure_ascii=False) + "\n")
                            log.flush()
                            termination = "bridge_unavailable"
                            break
                except (ValueError, TypeError, KeyError) as error:
                    log.write(json.dumps({"invalid_state": str(error)[:300]}, ensure_ascii=False) + "\n")
                    log.flush()
                    termination = "invalid_state"
                    break
            log.write(json.dumps({"summary": {"best_floor": best_floor,
                                                "actions": actions_done, "mode": mode,
                                                "started": started,
                                                "termination": termination}}, ensure_ascii=False) + "\n")
            log.flush()
            if experience:
                write_stream_status(status_path, run_number=run_number,
                                    state=last_state, action=last_display,
                                    source=last_source,
                                    reason=last_reason, experience=experience,
                                    last_fight=last_fight, memory_matches=last_matches,
                                    decision_ms=last_decision_ms,
                                    option_count=last_option_count,
                                    last_alice_action=last_alice_action,
                                    last_alice_reason=last_alice_reason,
                                    termination=termination)
    finally:
        if advisor:
            advisor.close()


def main():
    parser = argparse.ArgumentParser(description="Alice / Slay the Spire bridge")
    parser.add_argument("--mode", choices=("policy", "alice"),
                        default=os.environ.get("ALICE_STS_MODE", "alice"))
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--max-actions", type=int, default=MAX_RUN_ACTIONS)
    parser.add_argument("--pace-seconds", type=float,
                        default=float(os.environ.get("ALICE_STS_PACE_SECONDS", "2")))
    args = parser.parse_args()
    if not math.isfinite(args.pace_seconds) or not 0 <= args.pace_seconds <= 10:
        parser.error("--pace-seconds doit etre entre 0 et 10")
    run(args.mode, args.data_dir, args.max_actions, args.pace_seconds)


if __name__ == "__main__":
    main()
