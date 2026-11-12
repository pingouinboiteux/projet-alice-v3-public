"""Private, compact summary of Alice's Slay the Spire practice runs."""

import json
from pathlib import Path

from agent import DATA
from experience import Experience


def read_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except ValueError:
            continue
    return rows


def main():
    if not DATA.exists():
        print("Aucune partie enregistree.")
        return
    paths = sorted(DATA.glob("validation_run_*.jsonl"))
    if not paths:
        print("Aucune partie enregistree.")
        return
    print("Parties locales d'Alice (les essais interrompus ne mesurent pas sa force) :")
    complete_floors = []
    for path in paths[-12:]:
        rows = read_rows(path)
        actions = [row for row in rows if row.get("action")]
        summary = next((row["summary"] for row in reversed(rows) if "summary" in row), {})
        floor = int(summary.get("best_floor", max(
            (int(row.get("state", {}).get("floor", 0)) for row in actions), default=0)))
        outcome = summary.get("termination", "interrompue ou en cours")
        if outcome == "game_ended":
            complete_floors.append(floor)
        plays = sum(row["action"].startswith("PLAY ") for row in actions)
        model_plays = sum(row["action"].startswith("PLAY ") and row.get("source") == "model"
                          for row in actions)
        model = sum(row.get("source") == "model" for row in actions)
        print(f"- {path.stem}: etage {floor}, {plays} cartes dont {model_plays} choisies par Alice, "
              f"{model} decisions du modele, fin: {outcome}")
    if complete_floors:
        average = sum(complete_floors) / len(complete_floors)
        print(f"Etage moyen des {len(complete_floors)} parties terminees (anciens et nouveaux modes melanges): {average:.1f}")
    else:
        print("Aucune partie terminee; progression non encore mesurable.")
    learned = DATA / "learning.json"
    if learned.exists():
        cards = json.loads(learned.read_text(encoding="utf-8")).get("cards", {})
        print(f"Effets de cartes observes et conserves: {len(cards)}")
    memory = Experience(DATA / "experience.json")
    print(f"Experience visible conservee: {len(memory.fights)} combats, "
          f"{len(memory.pairs)} suites de cartes, {len(memory.runs)} parties terminees")
    floors = [run["floor"] for run in memory.runs if run.get("result") in ("defaite", "victoire")]
    if len(floors) >= 6:
        middle = len(floors) // 2
        early = sum(floors[:middle]) / middle
        recent = sum(floors[middle:]) / (len(floors) - middle)
        print(f"Etages moyens: debut {early:.1f}, parties recentes {recent:.1f} "
              "(indice, pas preuve de progression)")
    else:
        print(f"Progression: {len(floors)}/6 parties completes d'Alice pour un premier indice.")


if __name__ == "__main__":
    main()
