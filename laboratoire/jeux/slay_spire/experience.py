"""Bounded observations from visible Slay the Spire runs, never simulated play."""

import json
import os
from pathlib import Path


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Experience:
    MAX_FIGHTS = 200
    MAX_RUNS = 100
    MAX_PAIRS = 300

    def __init__(self, path):
        self.path = Path(path)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("version") != 1:
                raise ValueError("unknown experience version")
            self.fights = raw.get("fights", [])[-self.MAX_FIGHTS:]
            self.runs = raw.get("runs", [])[-self.MAX_RUNS:]
            self.pairs = raw.get("pairs", {})
            if not isinstance(self.fights, list) or not isinstance(self.runs, list) or not isinstance(self.pairs, dict):
                raise ValueError("invalid experience")
        except (OSError, ValueError, TypeError, AttributeError):
            self.fights, self.runs, self.pairs = [], [], {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "fights": self.fights[-self.MAX_FIGHTS:],
                   "runs": self.runs[-self.MAX_RUNS:], "pairs": self.pairs}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def observe_pair(self, previous_card, card, impact):
        if not previous_card or not card:
            return
        key = json.dumps([previous_card, card], ensure_ascii=False)
        item = self.pairs.get(key, {"count": 0, "impact": 0.0})
        count = max(0, int(_number(item.get("count")))) + 1
        old = _number(item.get("impact"))
        rate = 1.0 if count == 1 else min(0.2, 1.0 / count)
        estimate = old + rate * (max(-20.0, min(20.0, _number(impact))) - old)
        self.pairs[key] = {"count": count, "impact": round(estimate, 3)}
        while len(self.pairs) > self.MAX_PAIRS:
            self.pairs.pop(next(iter(self.pairs)))
        self.save()

    def pair_context(self, previous_card, hand):
        """Report observations, not causal claims about card synergies."""
        if not previous_card:
            return []
        result = []
        seen = set()
        for card in hand:
            card_id = card.get("id")
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            item = self.pairs.get(json.dumps([previous_card, card_id], ensure_ascii=False))
            if item and item.get("count", 0) >= 2:
                result.append({"after": previous_card, "card": card_id,
                               "observed_impact": item["impact"], "samples": item["count"]})
        return result[:8]

    def record_fight(self, fight, end_hp, won):
        entry = {"act": int(fight["act"]), "floor": int(fight["floor"]),
                 "enemies": sorted(set(fight["enemies"]))[:5],
                 "start_hp": int(fight["start_hp"]), "end_hp": int(max(0, end_hp)),
                 "hp_lost": int(max(0, fight["start_hp"] - min(fight.get("lowest_hp", end_hp), end_hp))),
                 "turns": int(fight["turns"]), "won": bool(won),
                 "cards": fight["cards"][:30]}
        self.fights.append(entry)
        self.fights = self.fights[-self.MAX_FIGHTS:]
        self.save()
        return entry

    def similar_fights(self, enemies):
        names = set(enemies)
        if not names:
            return []
        matches = [fight for fight in self.fights if names.intersection(fight.get("enemies", []))]
        return [{"enemies": fight["enemies"], "won": fight["won"],
                 "hp_lost": fight["hp_lost"], "turns": fight["turns"],
                 "first_cards": fight["cards"][:5]} for fight in matches[-2:]]

    def record_run(self, floor, result):
        self.runs.append({"floor": int(floor), "result": str(result)[:40]})
        self.runs = self.runs[-self.MAX_RUNS:]
        self.save()


def write_stream_status(path, *, run_number, state, action="", source="", reason="",
                        experience=None, last_fight=None, memory_matches=0, termination="",
                        decision_ms=0, option_count=0, last_alice_action="",
                        last_alice_reason=""):
    """Small UTF-8 text file suitable for OBS's read-from-file text source."""
    lines = ["ALICE • SLAY THE SPIRE", f"Partie visible n°{run_number}  |  Etage {state.get('floor', 0)}  |  PV {int(state.get('hp', 0))}"]
    if action:
        actor = "Alice (LLM)" if source == "model" else "automatique (option unique)"
        lines.append(f"{actor} : {action[:90]}")
        if source == "model":
            lines.append(f"Decision : {int(decision_ms)} ms, {int(option_count)} options")
    if reason and source == "model":
        lines.append(f"Pourquoi : {reason[:120]}")
    if source != "model" and last_alice_action:
        lines.append(f"Dernier choix d'Alice : {last_alice_action[:90]}")
        if last_alice_reason:
            lines.append(f"Pourquoi : {last_alice_reason[:120]}")
    if memory_matches:
        lines.append(f"Experiences comparables presentees : {memory_matches}")
    if last_fight:
        result = "gagne" if last_fight["won"] else "perdu"
        lines.append(f"Dernier combat : {result}, {last_fight['hp_lost']} PV perdus, {last_fight['turns']} tours")
    if experience:
        lines.append(f"Experience : {len(experience.fights)} combats, {len(experience.pairs)} suites de cartes observees")
        lines.append(f"Meilleur etage : {max((r['floor'] for r in experience.runs), default=0)}")
    if termination:
        lines.append(f"Fin : {termination}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temp, path)
