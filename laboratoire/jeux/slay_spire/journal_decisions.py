"""Readable audit of model calls and forced protocol actions in a visible run."""

import argparse
import json
from datetime import datetime

from agent import DATA


def main():
    parser = argparse.ArgumentParser(description="Journal des decisions d'Alice")
    parser.add_argument("--all", action="store_true", help="Afficher toute la partie")
    parser.add_argument("--detail", action="store_true", help="Afficher toutes les options et la reponse brute")
    args = parser.parse_args()
    paths = sorted(DATA.glob("validation_run_*.jsonl"))
    if not paths:
        print("Aucune partie enregistree.")
        return
    path = paths[-1]
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("action"):
            rows.append(row)
    model = [row for row in rows if row.get("source") == "model"]
    forced = [row for row in rows if row.get("source") == "forced"]
    card_plays = [row for row in rows if row["action"].startswith("PLAY ")]
    print(f"Partie : {path.name}")
    print(f"Actions : {len(rows)} | appels du modele : {len(model)} | "
          f"actions automatiques : {len(forced)}")
    print(f"Cartes jouees : {len(card_plays)}, dont "
          f"{sum(row.get('source') == 'model' for row in card_plays)} choisies par le modele")
    print("Les actions automatiques correspondent a une option unique du protocole.")
    print("L'heure indique le choix confirme ; l'envoi est la commande transmise au jeu.")
    print()
    for row in rows if args.all else rows[-50:]:
        decision = row.get("decision") or {}
        legacy = not decision
        try:
            stamp = datetime.fromisoformat(row["time"]).astimezone().strftime("%H:%M:%S")
        except (KeyError, ValueError):
            stamp = "--:--:--"
        actor = "ALICE/LLM" if row.get("source") == "model" else row.get("source", "?").upper()
        options = decision.get("options") or []
        chosen = decision.get("chosen_index")
        selected = next((item.get("action") for item in options
                         if item.get("index") == chosen), row["action"])
        if legacy:
            duration = "ancienne trace"
        elif row.get("source") == "model":
            duration = f"{decision.get('decision_ms', 0)} ms modele"
            if "delay_to_send_ms" in row:
                duration += f" + {row['delay_to_send_ms']} ms avant envoi"
            elif decision.get("paced_to_ms"):
                duration += f"; rythme cible {decision['paced_to_ms']} ms"
        else:
            duration = "option unique"
        print(f"{stamp}  {actor:11}  {selected}  [{duration}; {len(options)} options]")
        if row.get("command_sent_at"):
            sent_stamp = datetime.fromisoformat(row["command_sent_at"]).astimezone().strftime("%H:%M:%S.%f")[:-3]
            print(f"    Commande envoyee : {sent_stamp} | {row['action']}")
        if row.get("reason"):
            print(f"    Pourquoi : {row['reason']}")
        if args.detail:
            for item in options:
                marker = ">" if item.get("index") == chosen else " "
                print(f"    {marker} {item['index']}: {item['action']} ({item['command']})")
            if decision.get("raw_response"):
                print(f"    Reponse brute : {decision['raw_response']}")


if __name__ == "__main__":
    main()
