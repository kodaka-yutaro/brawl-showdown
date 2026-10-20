import copy
import unittest

from collect import normalize, valid_match, valid_shape


def battle(mode="soloShowdown", battle_type="ranked"):
    players = [
        {"tag": f"#P{i}", "brawler": {"id": 16000000 + i, "name": f"BRAWLER{i}", "trophies": 2000}}
        for i in range(10)
    ]
    result = {"mode": mode, "type": battle_type, "rank": 3}
    if mode == "soloShowdown":
        result["players"] = players
    else:
        result["teams"] = [players[i:i + 2] for i in range(0, 10, 2)]
    return {
        "battleTime": "20261020T090000.000Z",
        "event": {"id": 15000001, "mode": mode, "map": "Example Map"},
        "battle": result,
    }


class CollectFilteringTest(unittest.TestCase):
    def test_normal_solo_and_duo_keep_event_mode(self):
        for mode in ("soloShowdown", "duoShowdown"):
            with self.subTest(mode=mode):
                record = normalize(battle(mode))
                self.assertEqual(record["mode"], mode)
                self.assertEqual(record["eventMode"], mode)
                self.assertTrue(valid_match(record))

    def test_friendly_and_event_battles_are_excluded(self):
        for mode in ("soloShowdown", "duoShowdown"):
            for kind in ("friendly", "challenge", "championshipChallenge", "soloRanked", None):
                with self.subTest(mode=mode, kind=kind):
                    self.assertIsNone(normalize(battle(mode, kind)))

    def test_aliases_and_missing_event_modes_are_excluded(self):
        for mode, event_mode in (("soloShowdown", "hunterSurvivor"), ("duoShowdown", "trioShowdown"), ("soloShowdown", None)):
            item = battle(mode)
            item["event"]["mode"] = event_mode
            with self.subTest(mode=mode, event_mode=event_mode):
                self.assertIsNone(normalize(item))

    def test_other_modes_never_pass_even_with_duo_shape(self):
        for mode in ("brawlBall", "gemGrab", "trioShowdown", "hunterSurvivor", None):
            with self.subTest(mode=mode):
                item = battle(mode)
                self.assertFalse(valid_shape(mode, item["battle"]["teams"]))
                self.assertIsNone(normalize(item))

    def test_wrong_team_sizes_are_excluded(self):
        solo = battle()
        solo["battle"]["players"].pop()
        self.assertIsNone(normalize(solo))
        duo = battle("duoShowdown")
        duo["battle"]["teams"][0].append(duo["battle"]["teams"][1].pop())
        self.assertIsNone(normalize(duo))
        self.assertFalse(valid_shape("duoShowdown", None))

    def test_saved_records_preserve_legacy_and_reject_explicit_mismatches(self):
        record = normalize(battle("duoShowdown"))
        legacy = copy.deepcopy(record)
        del legacy["eventMode"]
        self.assertTrue(valid_match(legacy))
        for field, value in (("type", "friendly"), ("mode", "brawlBall"), ("eventMode", "trioShowdown"), ("eventMode", None)):
            changed = copy.deepcopy(record)
            changed[field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(valid_match(changed))

    def test_source_rank_checks_solo_and_both_duo_teammates(self):
        solo = normalize(battle(), "#P2")
        self.assertTrue(solo["rankOrderValid"])
        duo = battle("duoShowdown")
        duo["battle"]["rank"] = 2
        for source in ("#P2", "#P3"):
            with self.subTest(source=source):
                self.assertTrue(normalize(duo, source)["rankOrderValid"])
        self.assertNotIn("rankOrderValid", normalize(battle()))

    def test_unverified_rank_preserves_usage_but_marks_order_unusable(self):
        for source in ("#P0", "#MISSING"):
            with self.subTest(source=source):
                record = normalize(battle(), source)
                self.assertTrue(valid_match(record))
                self.assertFalse(record["rankOrderValid"])
        for mode in ("soloShowdown", "duoShowdown"):
            maximum = 10 if mode == "soloShowdown" else 5
            for rank in (None, 0, maximum + 1, -1, 2.5, "3", True):
                item = battle(mode)
                item["battle"]["rank"] = rank
                with self.subTest(mode=mode, rank=rank):
                    record = normalize(item, "#P2")
                    self.assertTrue(valid_match(record))
                    self.assertFalse(record["rankOrderValid"])


if __name__ == "__main__":
    unittest.main()
