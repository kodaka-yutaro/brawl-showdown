import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def match(mode, number, place, trophies=3000, rank_valid=None):
    solo = mode == "solo"
    teams = []
    for rank in range(1, 11 if solo else 6):
        team = []
        for member in range(1 if solo else 2):
            target = rank == place
            team.append({
                "tag": f"#{mode}-target-{member}" if target else f"#{mode}-{number}-{rank}-{member}",
                "brawler": ("A" if member == 0 else "B") if target else f"{mode}-{rank}-{member}",
                "trophies": trophies if target else 1500,
            })
        teams.append(team)
    time = f"20261020T{10 + number:02}0000.000Z"
    record = {
        "id": time + "|" + ",".join(p["tag"] for team in teams for p in team),
        "time": time,
        "mode": mode + "Showdown",
        "type": "ranked",
        "map": "Test",
        "teams": teams,
    }
    if rank_valid is not None:
        record["rankOrderValid"] = rank_valid
    return record


def build(matches):
    with tempfile.TemporaryDirectory(prefix="brawl-rank-test-") as folder:
        folder = Path(folder)
        src, dst = folder / "battles.jsonl.gz", folder / "data.json"
        with gzip.open(src, "wt") as stream:
            for record in matches:
                stream.write(json.dumps(record) + "\n")
        subprocess.run([
            sys.executable, str(ROOT / "build_data.py"), "--src", str(src),
            "--dst", str(dst), "--sample", "--keep-days", "0",
        ], check=True, capture_output=True, text=True)
        return json.loads(dst.read_text())


class AverageRankTests(unittest.TestCase):
    def test_weighted_sums_keep_legacy_usage_rows(self):
        data = build([
            match(mode, i, place, 3050 if i == 2 else 3000)
            for mode in ("solo", "duo") for i, place in enumerate((1, 3, 3))
        ])
        a = next(i for i, item in enumerate(data["brawlers"]) if item["name"] == "A")
        for view in ("solo", "duo", "pair"):
            with self.subTest(view=view):
                rows = data[view]
                indexes = [i for i, row in enumerate(rows) if row[2] == a]
                self.assertEqual(len(data["rankSums"][view]), len(rows))
                self.assertEqual(sum(rows[i][-1] for i in indexes), 3)
                self.assertEqual(sum(data["rankSums"][view][i] for i in indexes), 7)
                self.assertTrue(all(len(row) == (6 if view == "pair" else 5) for row in rows))

    def test_invalid_rank_order_preserves_usage_and_marks_rank_unknown(self):
        for bad_index in (0, 4):
            data = build([
                match(mode, i, place, rank_valid=i != bad_index)
                for mode in ("solo", "duo") for i, place in enumerate((1, 3, 3, 2, 4))
            ])
            a = next(i for i, item in enumerate(data["brawlers"]) if item["name"] == "A")
            for view in ("solo", "duo", "pair"):
                with self.subTest(bad_index=bad_index, view=view):
                    indexes = [i for i, row in enumerate(data[view]) if row[2] == a]
                    self.assertEqual(sum(data[view][i][-1] for i in indexes), 5)
                    self.assertTrue(all(data["rankSums"][view][i] is None for i in indexes))
                    accounts = [row for row in data["accounts"][view] if row[2] == a]
                    self.assertEqual(len(accounts), 5)
                    self.assertEqual(sum(row[-1] is None for row in accounts), 1)


if __name__ == "__main__":
    unittest.main()
