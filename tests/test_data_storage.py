import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from data_storage import FILES, pack, restore
from test_average_rank import match


ROOT = Path(__file__).resolve().parents[1]


class DataStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        records = [match("solo", i, 1) for i in range(6)]
        (self.data / "battles.jsonl.gz").write_bytes(gzip.compress(
            "".join(json.dumps(m) + "\n" for m in records).encode(), mtime=0))
        (self.data / "names.json").write_text(json.dumps({"#solo-target-0": "悠太郎🐹", "#UNUSED": "unused"}))
        (self.data / "brawlers.json").write_text('{"A":16000000}')

    def test_legacy_migration_multiple_parts_and_exact_round_trip(self):
        expected = {name: (self.data / name).read_bytes() for name in FILES}
        restore(self.data)
        pack(self.data, chunk_bytes=40)
        parts = list((self.data / "archive").glob("*.part"))
        self.assertGreater(len(parts), 3)
        self.assertTrue(all(p.stat().st_size <= 40 for p in parts))
        for name in FILES:
            (self.data / name).unlink()
        restore(self.data)
        self.assertEqual(expected, {name: (self.data / name).read_bytes() for name in FILES})
        # Repacking removes obsolete parts if a source shrinks.
        (self.data / "names.json").write_text("{}")
        pack(self.data, chunk_bytes=40)
        manifest = json.loads((self.data / "archive/manifest.json").read_text())
        self.assertEqual(
            {p.name for p in (self.data / "archive").glob("*.part")},
            {p["name"] for f in manifest["files"].values() for p in f["parts"]},
        )

    def test_corruption_never_replaces_working_files(self):
        pack(self.data, chunk_bytes=40)
        part = next((self.data / "archive").glob("names.json.*.part"))
        part.write_bytes(b"X" * part.stat().st_size)
        expected = {name: (self.data / name).read_bytes() for name in FILES}
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            restore(self.data)
        self.assertEqual(expected, {name: (self.data / name).read_bytes() for name in FILES})

    def test_missing_part_or_manifest_fails_closed(self):
        pack(self.data, chunk_bytes=40)
        next((self.data / "archive").glob("*.part")).unlink()
        with self.assertRaises(FileNotFoundError):
            restore(self.data)
        (self.data / "archive/manifest.json").unlink()
        with self.assertRaises(FileNotFoundError):
            restore(self.data)

    def test_build_preserves_statistics_and_active_names_after_migration(self):
        def build():
            dst = self.data / "site.json"
            subprocess.run([
                sys.executable, str(ROOT / "build_data.py"), "--src", str(self.data / "battles.jsonl.gz"),
                "--dst", str(dst), "--sample",
            ], check=True, capture_output=True)
            result = json.loads(dst.read_text())
            result.pop("updated")
            return result
        before = build()
        self.assertEqual(json.loads((self.data / "names.json").read_text()), {"#solo-target-0": "悠太郎🐹"})
        self.assertIn(["#solo-target-0", "悠太郎🐹"], before["players"])
        pack(self.data, chunk_bytes=40)
        for name in FILES:
            (self.data / name).unlink()
        restore(self.data)
        self.assertEqual(build(), before)


if __name__ == "__main__":
    unittest.main()
