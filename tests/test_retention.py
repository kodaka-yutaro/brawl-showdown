import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from build_data import load_matches
from test_average_rank import match


class RetentionTests(unittest.TestCase):
    def test_ten_day_boundary_and_persisted_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "battles.jsonl.gz"
            records = []
            for i, stamp in enumerate(("20261022T120000.000Z", "20261012T120000.000Z", "20261012T115959.000Z")):
                record = match("solo", i, 1)
                record["time"] = stamp
                record["id"] = stamp + "|" + record["id"].split("|", 1)[1]
                records.append(record)
            invalid = copy.deepcopy(records[0])
            invalid["type"] = "friendly"
            with gzip.open(src, "wt") as f:
                for record in records + [records[0], invalid]:
                    f.write(json.dumps(record) + "\n")
            kept, latest = load_matches(src, 10)
            self.assertEqual(latest.strftime("%Y%m%dT%H%M%S"), "20261022T120000")
            self.assertEqual([json.loads(line)["time"] for line in kept], [records[1]["time"], records[0]["time"]])
            with gzip.open(src, "rt") as f:
                self.assertEqual(f.readlines(), kept)
            self.assertEqual(load_matches(src, 10)[0], kept)

    def test_keep_zero_keeps_old_records(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "battles.jsonl.gz"
            records = [match("solo", 0, 1), match("solo", 1, 1)]
            records[0]["time"] = "20200101T000000.000Z"
            with gzip.open(src, "wt") as f:
                f.writelines(json.dumps(m) + "\n" for m in records)
            self.assertEqual(len(load_matches(src, 0)[0]), 2)


if __name__ == "__main__":
    unittest.main()
