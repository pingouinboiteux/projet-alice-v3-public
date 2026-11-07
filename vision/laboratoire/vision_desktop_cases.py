"""Four synthetic desktop OCR stress cases; no captures or personal content.

1920x1080 fixtures deliberately use 14-18 px text, varied pane positions and
themes. Expectations follow vision_bench_cases.score_case. Freeze this lot
before measurement; do not use its failures to tune the tested candidate.
"""
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


def generate_cases(output_dir: str | Path, split: str = "desktop") -> list[dict]:
    if split != "desktop":
        raise ValueError("This fixed robustness lot supports only desktop")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(982734)
    fonts = {size: ImageFont.load_default(size=size) for size in (14, 16, 18)}
    cases = []
    for index in range(4):
        dark = index % 2 == 1
        background, panel, ink, muted = (("#19212e", "#283244", "#f3f5f8", "#bec8d7") if dark
                                          else ("#dce5ef", "#ffffff", "#172331", "#4d5b6b"))
        image = Image.new("RGB", (1920, 1080), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1919, 38), fill="#111925")
        draw.text((22, 11), "Bureau de demonstration - documents fictifs", fill="white", font=fonts[14])
        draw.text((1770, 11), "13:47", fill="white", font=fonts[14])
        draw.rectangle((0, 1018, 1919, 1079), fill="#111925")
        draw.text((28, 1040), "Accueil     Fichiers     Notes     Agenda", fill="white", font=fonts[14])
        draw.rectangle((25, 85, 235, 470), fill=panel)
        for row, label in enumerate(["Raccourcis", "Documents", "Images", "Archives", "Corbeille", "Aucune alerte"]):
            draw.text((43, 110+row*47), label, fill=muted, font=fonts[14])
        x, y = [(355, 125), (895, 260), (480, 310), (1010, 90)][index]
        draw.rectangle((x, y, x+780, y+630), fill=panel, outline=muted, width=1)
        draw.rectangle((x, y, x+780, y+41), fill="#335b80")
        title = "Courrier - message ouvert" if index < 2 else "Navigateur - menu du cafe"
        draw.text((x+18, y+12), title, fill="white", font=fonts[18])
        draw.text((x+725, y+12), "_  X", fill="white", font=fonts[16])
        if index < 2:
            name = ["Elise", "Bastien"][index]
            hour = f"{rng.randrange(8, 19):02d}:{rng.choice(['05', '15', '35', '45'])}"
            room = f"T{rng.randrange(210, 890)}"
            size = 16 if index == 0 else 14
            lines = [f"De : {name}", "A : accueil", "Objet : preparation de la visite", "",
                     "Bonjour,", "Voici les informations pour notre rendez-vous.",
                     f"Heure : {hour}", f"Salle : {room}", "Merci de confirmer votre presence.",
                     "Bonne journee."]
            for row, line in enumerate(lines):
                draw.text((x+34, y+78+row*37), line, fill=ink, font=fonts[size])
            expected = {"expediteur": name, "heure": hour, "salle": room}
            question = ('Lis le message ouvert dans la fenetre Courrier. Donne son expediteur, '
                        'l heure du rendez-vous et la salle. Ignore l horloge du bureau. '
                        'Format : {"expediteur": string, "heure": string, "salle": string}.')
            category = "ocr_mail"
        else:
            dish = ["Risotto", "Clafoutis"][index-2]
            price = f"{rng.randrange(6, 18)},{rng.choice(['30', '60', '90'])} EUR"
            draw.rectangle((x+18, y+58, x+760, y+91), outline=muted)
            draw.text((x+31, y+67), "https://cafe-fictif.example/menu", fill=muted, font=fonts[14])
            draw.text((x+35, y+125), "MENU DU CAFE", fill=ink, font=fonts[18])
            size = 14 if index == 2 else 16
            lines = ["Cuisine maison - service du midi", "", "Plat / dessert du jour", f"{dish} : {price}",
                     "Eau : 2,00 EUR", "Cafe : 3,50 EUR", "", "Les commandes se font au comptoir."]
            for row, line in enumerate(lines):
                draw.text((x+35, y+180+row*39), line, fill=ink, font=fonts[size])
            expected = {"prix": price}
            question = (f'Lis le menu dans la fenetre du navigateur. Quel est le prix de {dish} ? '
                        'Conserve la devise visible. Format : {"prix": string}.')
            category = "ocr_menu"
        path = output / f"case_{index+1:03d}.png"
        image.save(path)
        cases.append({"id": f"desktop_{index+1:03d}", "category": category,
                      "image_path": path.as_posix(), "question": question +
                      " Reponds uniquement avec cet objet JSON, sans commentaire ni Markdown.",
                      "expected": expected, "scoring": {key: "text" for key in expected}})
    return cases
