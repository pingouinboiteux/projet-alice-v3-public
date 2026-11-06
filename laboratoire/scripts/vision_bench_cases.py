"""Small synthetic vision instrument; no captures, models, memory or network.

generate_cases(directory, 'calibration'|'heldout') writes 14 PNGs. Use only
request_for_case(case) for the model request: expected/scoring stay local.
The heldout set uses distinct content and seeds, not a random train/test split.
score_case accepts an already parsed strict JSON object. Field scores are useful
for diagnosis; passed requires every field and exactly the requested keys.
These simple scenes do not qualify real games, natural photos or chess rules.
"""
from __future__ import annotations

import math
import random
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SPLIT_SEEDS = {"calibration": 73121, "heldout": 94817}
SIZE = (768, 512)


def normalize_text(value: str) -> str:
    """Ignore case/whitespace, but preserve digits, accents and punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def request_for_case(case: dict) -> dict:
    """Allowlist model-visible input; never serialize the complete case."""
    return {"image_path": case["image_path"], "question": case["question"]}


def score_case(case: dict, parsed: object) -> dict:
    """Deterministic factual scoring; no LLM judge or substring matching.

    Coordinate lists are [x,y] pixels, accepted within Euclidean tolerance.
    Other lists are exact ordered lists. Booleans cannot stand in for integers.
    Unknown information must be JSON null, not an invented answer.
    """
    expected = case["expected"]
    valid_object = isinstance(parsed, dict)
    schema_ok = valid_object and set(parsed) == set(expected)
    fields = {}
    for key, wanted in expected.items():
        actual = parsed.get(key) if valid_object else None
        present = valid_object and key in parsed
        kind = case["scoring"][key]
        correct = False
        if present and kind == "text":
            correct = isinstance(actual, str) and normalize_text(actual) == normalize_text(wanted)
        elif present and kind == "point":
            if isinstance(actual, list) and len(actual) == 2 and all(
                type(v) in (int, float) and -1e9 <= v <= 1e9 and math.isfinite(v) for v in actual
            ):
                correct = math.dist(actual, wanted) <= case.get("coordinate_tolerance", 12)
        elif present:
            correct = type(actual) is type(wanted) and actual == wanted
            if isinstance(wanted, list) and correct:
                correct = all(type(a) is type(b) for a, b in zip(actual, wanted))
        fields[key] = bool(correct)
    return {"passed": bool(schema_ok and all(fields.values())),
            "schema_ok": bool(schema_ok), "score": sum(fields.values()) / len(fields),
            "fields": fields}


def generate_cases(output_dir: str | Path, split: str = "calibration") -> list[dict]:
    """Write reproducible RGB images and return local case records.

    Pass separate directories for the two splits; paths are stored as provided.
    Pillow >=10.1 supplies its bundled font, avoiding OS font dependencies.
    PNGs contain no ground-truth metadata; generic filenames encode only order.
    """
    if split not in SPLIT_SEEDS:
        raise ValueError("split must be calibration or heldout")
    rng = random.Random(SPLIT_SEEDS[split])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=26)
    small = ImageFont.load_default(size=22)
    cases = []

    def canvas():
        im = Image.new("RGB", SIZE, "white")
        return im, ImageDraw.Draw(im)

    def save(im, category, question, expected, scoring):
        index = len(cases) + 1
        path = output / f"case_{index:03d}.png"
        im.save(path)
        cases.append({"id": f"{split}_{index:03d}", "category": category,
                      "image_path": path.as_posix(), "question": question +
                      " Reponds uniquement avec cet objet JSON, sans commentaire ni Markdown.",
                      "expected": expected, "scoring": scoring,
                      "coordinate_tolerance": 12})

    names = ["Lina", "Hugo"] if split == "calibration" else ["Nora", "Remi"]
    for i in range(2):
        im, draw = canvas()
        hour = f"{rng.randrange(8, 19):02d}:{rng.choice(['10', '25', '40', '55'])}"
        code = f"R{rng.randrange(100, 999)}"
        lines = ["COURRIER", f"De : {names[i]}", "Objet : rendez-vous",
                 f"Bonjour, rendez-vous a {hour}.", f"Salle : {code}", "Merci !"]
        for row, line in enumerate(lines):
            draw.text((40, 35 + row * 60), line, fill="black", font=font)
        save(im, "ocr_mail", 'Lis le courrier. Format : {"expediteur": string, "heure": string, "salle": string}.',
             {"expediteur": names[i], "heure": hour, "salle": code},
             {"expediteur": "text", "heure": "text", "salle": "text"})

    dishes = ["Soupe", "Tarte"] if split == "calibration" else ["Salade", "Flan"]
    for dish in dishes:
        im, draw = canvas()
        price = f"{rng.randrange(4, 16)},{rng.choice(['20', '50', '80'])} EUR"
        for row, line in enumerate(["MENU DU JOUR", f"{dish} : {price}", "Eau : 2,00 EUR", "Cafe : 3,00 EUR"]):
            draw.text((45, 50 + row * 75), line, fill="black", font=font)
        save(im, "ocr_menu", f'Quel est le prix de {dish} ? Format : {{"prix": string}}. Conserve la devise visible.',
             {"prix": price}, {"prix": "text"})

    for i in range(4):
        im, draw = canvas()
        # Distinct cells ensure unambiguous shapes and relations with no overlap.
        cells = [(110, 130), (330, 130), (570, 130), (110, 350), (330, 350), (570, 350)]
        rng.shuffle(cells)
        red, blue = cells[:2]
        count = rng.randrange(1, 4)
        draw.ellipse((red[0]-32, red[1]-32, red[0]+32, red[1]+32), fill="#e02020")
        draw.rectangle((blue[0]-32, blue[1]-32, blue[0]+32, blue[1]+32), fill="#2040e0")
        for x, y in cells[2:2+count]:
            draw.polygon([(x, y-35), (x-35, y+30), (x+35, y+30)], fill="#169030")
        save(im, "spatial", 'Image 768x512 pixels, origine en haut a gauche. Donne le centre du cercle rouge, le nombre de triangles verts et si le cercle rouge est strictement a gauche du carre bleu. Format : {"centre": [x,y], "triangles": integer, "a_gauche": boolean}.',
             {"centre": list(red), "triangles": count, "a_gauche": red[0] < blue[0]},
             {"centre": "point", "triangles": "exact", "a_gauche": "exact"})

    for i in range(4):
        im, draw = canvas()
        occupied = rng.sample(range(64), 5 + i)
        for row in range(8):
            for col in range(8):
                x, y = 180 + col * 50, 40 + row * 50
                draw.rectangle((x, y, x+49, y+49), fill="#dbd5bf" if (row+col)%2 == 0 else "#7c927d")
                if row*8+col in occupied:
                    draw.ellipse((x+12, y+12, x+38, y+38), fill="black", outline="white", width=2)
            draw.text((146, 52+row*50), str(8-row), font=small, fill="black")
        for col in range(8):
            draw.text((198+col*50, 446), chr(97+col), font=small, fill="black")
        target = occupied[0] if i % 2 == 0 else next(n for n in range(64) if n not in occupied)
        square = chr(97+target%8) + str(8-target//8)
        save(im, "board_occupancy", f'Ce damier contient des pions ronds noirs. Combien de pions au total et la case {square} est-elle occupee ? Format : {{"nombre": integer, "occupee": boolean}}.',
             {"nombre": len(occupied), "occupee": target in occupied},
             {"nombre": "exact", "occupee": "exact"})
        # Local scoring metadata only: never included by request_for_case.
        cases[-1]["board_query_square"] = square
        cases[-1]["board_occupied_truth"] = sorted(
            chr(97+n%8) + str(8-n//8) for n in occupied)

    im, draw = canvas()
    draw.text((50, 80), "Code secret :", font=font, fill="black")
    draw.rectangle((50, 140, 440, 205), fill="#444444")
    draw.text((50, 250), "Zone entierement masquee", font=font, fill="black")
    save(im, "unknown_occluded", 'Quel code est cache sous le rectangle opaque ? Si impossible a lire, utilise null. Format : {"code": string ou null}.',
         {"code": None}, {"code": "exact"})
    im, draw = canvas()
    draw.text((50, 75), "Livraison", font=font, fill="black")
    draw.text((50, 155), f"Destinataire : {names[0]}", font=font, fill="black")
    draw.text((50, 235), "Date : non renseignee", font=font, fill="black")
    save(im, "unknown_absent", 'Quelle est la date de livraison ? Si absente, utilise null. Format : {"date": string ou null}.',
         {"date": None}, {"date": "exact"})
    return cases
