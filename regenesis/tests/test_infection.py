"""Run with: python -m unittest discover -s regenesis/tests -v"""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infection import InfectionState, stage


class InfectionTests(unittest.TestCase):
    def test_stage_boundaries(self):
        self.assertEqual([stage(x) for x in (0, 24, 25, 49, 50, 74, 75, 100)],
                         ["clean", "clean", "exposed", "exposed", "infested", "infested", "overrun", "overrun"])

    def test_independent_rooms_and_cap(self):
        state = InfectionState()
        self.assertEqual(state.advance("museum", 20), 100)
        self.assertEqual(state.level("street"), 0)
        self.assertEqual(state.visual_stage("museum"), "overrun")

    def test_negative_encounters_rejected(self):
        with self.assertRaises(ValueError):
            InfectionState().advance("museum", -1)

    def test_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = InfectionState({"museum": 42})
            state.save(path)
            self.assertEqual(InfectionState.load(path).rooms, {"museum": 42})

    def test_invalid_schema_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"version":1,"rooms":{"museum":"bad"}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                InfectionState.load(path)


if __name__ == "__main__":
    unittest.main()
