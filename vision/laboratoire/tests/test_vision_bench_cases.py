"""Synthetic instrument checks, independent of a model or live services."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from vision.laboratoire.vision_bench_cases import generate_cases, request_for_case, score_case


class VisionBenchCasesTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "laboratoire" / "data" / "validation"
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="validation_vision_cases_", dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cases = generate_cases(self.root / "calibration")

    def test_deterministic_and_heldout_content_distinct(self):
        same = generate_cases(self.root / "again")
        heldout = generate_cases(self.root / "heldout", "heldout")
        digest = lambda case: hashlib.sha256(Path(case["image_path"]).read_bytes()).hexdigest()
        self.assertEqual(len(self.cases), 14)
        self.assertEqual([digest(c) for c in self.cases], [digest(c) for c in same])
        self.assertNotEqual([digest(c) for c in self.cases[:12]], [digest(c) for c in heldout[:12]])
        self.assertTrue(all(a["expected"] != b["expected"] for a, b in zip(self.cases[:4], heldout[:4])))
        for case in self.cases:
            self.assertTrue(score_case(case, copy.deepcopy(case["expected"]))["passed"])
            self.assertEqual(set(request_for_case(case)), {"question", "image_path"})

    def test_missing_extra_wrong_types_and_partial_rejected(self):
        case = self.cases[4]
        expected = case["expected"]
        for result in [None, [], {}, {"triangles": expected["triangles"]},
                       {**expected, "extra": "invented"}, {**expected, "triangles": True},
                       {**expected, "triangles": str(expected["triangles"])}]:
            self.assertFalse(score_case(case, result)["passed"], result)
        self.assertGreater(score_case(case, {"triangles": expected["triangles"]})["score"], 0)

    def test_ocr_exact_with_whitespace_and_case_normalization_only(self):
        case = self.cases[0]
        answer = {k: "  " + v.upper() + " \n" for k, v in case["expected"].items()}
        self.assertTrue(score_case(case, answer)["passed"])
        answer["salle"] += " et une autre"
        self.assertFalse(score_case(case, answer)["passed"])

    def test_coordinate_euclidean_tolerance_and_nonfinite_rejected(self):
        case = self.cases[4]
        expected = case["expected"]
        x, y = expected["centre"]
        for point, wanted in [([x+12, y], True), ([x+9, y+9], False),
                              ([float("nan"), y], False), ([float("inf"), y], False),
                              ([True, y], False), ([x], False), ([str(x), y], False),
                              ([10**1000, y], False)]:
            self.assertEqual(score_case(case, {**expected, "centre": point})["passed"], wanted)

    def test_unknown_requires_explicit_null(self):
        case = self.cases[12]
        self.assertTrue(score_case(case, {"code": None})["passed"])
        for answer in [{}, {"code": "inconnu"}, {"code": "1234"}]:
            self.assertFalse(score_case(case, answer)["passed"])

    def test_invalid_split_rejected_before_writing(self):
        with self.assertRaises(ValueError):
            generate_cases(self.root / "bad", "training")
        self.assertFalse((self.root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
