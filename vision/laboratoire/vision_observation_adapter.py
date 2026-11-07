"""Explicit native observation protocol; never guess coordinate conventions.

Use build_question before inference and decode_response afterward as a pair.
Only spatial/board observation contracts change. Ground truth is accessed only
by score_board_set, not by prompts or decoding. Baseline questions stay intact.
"""
from __future__ import annotations

import math
import re

from vision.laboratoire.vision_bench_cases import SIZE


def build_question(case: dict) -> str:
    if case["category"] == "spatial":
        return ('Donne le centre du cercle rouge en coordonnees NORMALISEES de 0 a 1000 '
                'sur chaque axe : x=0 a gauche, x=1000 a droite, y=0 en haut, y=1000 en bas. '
                'Donne aussi le nombre de triangles verts et si le cercle rouge est strictement '
                'a gauche du carre bleu. Reponds uniquement avec cet objet JSON : '
                '{"centre": [x,y], "triangles": integer, "a_gauche": boolean}.')
    if case["category"] == "board_occupancy":
        return ('Lis les lettres et les chiffres du damier. Enumere TOUTES les cases '
                'contenant un pion rond noir, une seule fois chacune. Ne compte pas '
                'les cases vides. Reponds uniquement avec cet objet JSON : '
                '{"cases": ["a1", "b2", ...]}. Les noms dans cet exemple illustrent '
                'seulement le format, pas la reponse.')
    return case["question"]


def _board_squares(parsed: object) -> list[str]:
    if not isinstance(parsed, dict) or set(parsed) != {"cases"}:
        raise ValueError("Expected only the cases field")
    squares = parsed["cases"]
    if not isinstance(squares, list) or len(squares) > 64:
        raise ValueError("Expected at most 64 board squares")
    if any(not isinstance(square, str) or re.fullmatch(r"[a-h][1-8]", square) is None
           for square in squares):
        raise ValueError("Invalid square; expected a1 through h8")
    if len(set(squares)) != len(squares):
        raise ValueError("Duplicate occupied square")
    return squares


def decode_response(case: dict, parsed: object, image_size=SIZE) -> object:
    """Convert explicitly requested native observations into baseline fields.

    Coordinates are always scaled, even when values happen to look like pixels.
    Malformed native responses raise ValueError; no repair or hidden truth use.
    """
    category = case["category"]
    if category == "spatial":
        if len(image_size) != 2 or any(type(v) is not int or v <= 0 for v in image_size):
            raise ValueError("Invalid source image dimensions")
        if not isinstance(parsed, dict) or set(parsed) != {"centre", "triangles", "a_gauche"}:
            raise ValueError("Invalid spatial fields")
        point = parsed["centre"]
        if not isinstance(point, list) or len(point) != 2 or any(
            type(v) not in (int, float) or not 0 <= v <= 1000 or not math.isfinite(v)
            for v in point
        ):
            raise ValueError("Expected two finite coordinates between 0 and 1000")
        if type(parsed["triangles"]) is not int or parsed["triangles"] < 0:
            raise ValueError("Invalid triangle count")
        if type(parsed["a_gauche"]) is not bool:
            raise ValueError("Invalid left relation")
        return {**parsed, "centre": [point[0] * image_size[0] / 1000,
                                     point[1] * image_size[1] / 1000]}
    if category == "board_occupancy":
        squares = _board_squares(parsed)
        query = case["board_query_square"]
        if not isinstance(query, str) or re.fullmatch(r"[a-h][1-8]", query) is None:
            raise ValueError("Invalid local query square")
        return {"nombre": len(squares), "occupee": query in squares}
    return parsed


def score_board_set(case: dict, parsed: object) -> dict:
    """Extra factual metric, independent of count and one queried square."""
    if case["category"] != "board_occupancy":
        raise ValueError("Exact board score applies only to board cases")
    actual = set(_board_squares(parsed))
    truth = set(case["board_occupied_truth"])
    return {"passed": actual == truth, "missing": sorted(truth-actual),
            "extra": sorted(actual-truth)}
