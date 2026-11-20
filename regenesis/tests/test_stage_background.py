import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage_background import stage_background


class BackgroundStagingTests(unittest.TestCase):
    def test_preview_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "custom.png"
            source.write_bytes(b"sample placeholder bytes")
            dest = stage_background(source, root, "confirmed.png", "infested")
            self.assertEqual(dest.read_bytes(), source.read_bytes())
            with self.assertRaises(FileExistsError):
                stage_background(source, root, "confirmed.png", "infested")

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "custom.png"
            source.write_bytes(b"placeholder")
            with self.assertRaises(ValueError):
                stage_background(source, Path(temp), "../bad.png", "exposed")

    def test_apply_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "custom.webp"
            source.write_bytes(b"placeholder")
            dest = stage_background(source, root, "confirmed.webp", "overrun", apply=True)
            self.assertEqual(dest, root / "mods/layeredfs/romfs/HD_BACKGROUNDS/confirmed.webp")


if __name__ == "__main__":
    unittest.main()
