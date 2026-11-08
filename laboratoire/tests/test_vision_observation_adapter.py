"""Pure native protocol tests: no model or services."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from vision_observation_adapter import build_question, decode_response, score_board_set


class ObservationAdapterTests(unittest.TestCase):
    def test_explicit_normalized_coordinates_scaled_even_if_pixel_like(self):
        case = {"category": "spatial"}
        self.assertIn("1000", build_question(case))
        parsed = {"centre": [500, 500], "triangles": 3, "a_gauche": True}
        self.assertEqual(decode_response(case, parsed)["centre"], [384, 256])
        parsed["centre"] = [330, 350]
        self.assertEqual(decode_response(case, parsed)["centre"], [253.44, 179.2])
        self.assertEqual(parsed["centre"], [330, 350])

    def test_invalid_points_rejected(self):
        for point in [[-1, 3], [1001, 3], [float("nan"), 3], [float("inf"), 3],
                      [True, 3], [10**1000, 3], [3], ["3", 4], None]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                decode_response({"category": "spatial"},
                                {"centre": point, "triangles": 1, "a_gauche": False})

    def test_actual_dimensions_used_for_conversion(self):
        parsed = {"centre": [250, 750], "triangles": 1, "a_gauche": False}
        decoded = decode_response({"category": "spatial"}, parsed, image_size=(1920, 1080))
        self.assertEqual(decoded["centre"], [480, 810])
        for size in [(0, 1080), (-1, 1080), (1920,), (1920.0, 1080), (True, 1080)]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                decode_response({"category": "spatial"}, parsed, image_size=size)

    def test_bad_schema_and_types_rejected(self):
        good = {"centre": [100, 200], "triangles": 1, "a_gauche": False}
        for answer in [None, {}, {**good, "extra": 1}, {**good, "triangles": True},
                       {**good, "triangles": -1}, {**good, "a_gauche": 0}]:
            with self.assertRaises(ValueError):
                decode_response({"category": "spatial"}, answer)

    def test_board_decoding_needs_no_ground_truth(self):
        case = {"category": "board_occupancy", "board_query_square": "c4"}
        self.assertEqual(decode_response(case, {"cases": ["a1", "c4"]}),
                         {"nombre": 2, "occupee": True})
        self.assertEqual(decode_response(case, {"cases": []}),
                         {"nombre": 0, "occupee": False})
        self.assertNotIn("c4", build_question(case))

    def test_board_duplicates_invalid_names_and_extra_fields_rejected(self):
        case = {"category": "board_occupancy", "board_query_square": "a1"}
        for answer in [{"cases": ["a1", "a1"]}, {"cases": ["i1"]},
                       {"cases": ["a9"]}, {"cases": ["A1"]}, {"cases": [1]},
                       {"cases": "a1"}, {"cases": [], "extra": 1}, {}]:
            with self.assertRaises(ValueError):
                decode_response(case, answer)

    def test_exact_board_set_rejects_right_count_wrong_locations(self):
        case = {"category": "board_occupancy", "board_query_square": "a1",
                "board_occupied_truth": ["a1", "c4"]}
        wrong = {"cases": ["a1", "d4"]}
        self.assertEqual(decode_response(case, wrong), {"nombre": 2, "occupee": True})
        self.assertEqual(score_board_set(case, wrong),
                         {"passed": False, "missing": ["c4"], "extra": ["d4"]})
        self.assertTrue(score_board_set(case, {"cases": ["c4", "a1"]})["passed"])

    def test_untouched_categories_passthrough(self):
        case = {"category": "ocr_mail", "question": "baseline unchanged"}
        self.assertEqual(build_question(case), case["question"])
        answer = {"expediteur": "Nora"}
        self.assertIs(decode_response(case, answer), answer)


if __name__ == "__main__":
    unittest.main()
