"""Relocation checks using synthetic observations; no model or services."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("first", ["vision_observation_adapter",
                                  "vision.laboratoire.vision_observation_adapter"])
def test_import_order_helpers_and_patch(first):
    code = f'''
import importlib
import sys
from unittest.mock import patch
sys.path.insert(0, {str(ROOT)!r})
if {first!r}.startswith('vision.'):
    importlib.import_module({first!r})
sys.path.insert(0, {str(ROOT / 'laboratoire/scripts')!r})
importlib.import_module({first!r})
legacy = importlib.import_module('vision_observation_adapter')
canonical = importlib.import_module('vision.laboratoire.vision_observation_adapter')
assert legacy is canonical
assert legacy._board_squares is canonical._board_squares
original = canonical._board_squares
with patch('vision_observation_adapter._board_squares', return_value=['b2']):
    case = {{'category': 'board_occupancy', 'board_query_square': 'b2'}}
    assert canonical.decode_response(case, {{'cases': []}}) == {{'nombre': 1, 'occupee': True}}
assert canonical._board_squares is original
'''
    subprocess.run([sys.executable, "-c", code], cwd=ROOT / "vision", check=True)


def test_protocol_through_canonical_and_runtime_imports():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "laboratoire/scripts"))
    from vision.laboratoire import vision_observation_adapter as canonical
    from vision_observation_adapter import build_question, decode_response, score_board_set

    assert build_question is canonical.build_question
    assert decode_response is canonical.decode_response
    assert score_board_set is canonical.score_board_set
    spatial = {"category": "spatial"}
    answer = {"centre": [250, 750], "triangles": 2, "a_gauche": False}
    assert "1000" in build_question(spatial)
    assert decode_response(spatial, answer)["centre"] == [192, 384]
    assert decode_response(spatial, answer, (1920, 1080))["centre"] == [480, 810]
    assert answer["centre"] == [250, 750]
    with pytest.raises(ValueError):
        decode_response(spatial, {**answer, "centre": [1001, 0]})
    board = {"category": "board_occupancy", "board_query_square": "d5",
             "board_occupied_truth": ["a1", "d5"]}
    assert decode_response(board, {"cases": ["d5"]}) == {"nombre": 1, "occupee": True}
    assert score_board_set(board, {"cases": ["d5", "h8"]}) == {
        "passed": False, "missing": ["a1"], "extra": ["h8"]}
    with pytest.raises(ValueError):
        decode_response(board, {"cases": ["d5", "d5"]})
    passthrough = {"category": "validation_other", "question": "validation_question"}
    assert build_question(passthrough) == "validation_question"
    assert decode_response(passthrough, answer) is answer
