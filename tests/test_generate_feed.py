import copy
import datetime as dt
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_feed as gf  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
LIBRARY = json.loads((ROOT / "content" / "library.json").read_text(encoding="utf-8"))
DAY = dt.date(2026, 11, 15)


class LibraryTests(unittest.TestCase):
    def test_real_library_is_valid(self):
        entries, _ = gf.validate_library(LIBRARY, CONFIG)
        self.assertGreaterEqual(len(entries), 9)

    def test_rejects_empty_text(self):
        lib = copy.deepcopy(LIBRARY)
        lib["entries"][0]["text"] = "   "
        with self.assertRaises(gf.ValidationError):
            gf.validate_library(lib, CONFIG)

    def test_rejects_duplicate_id(self):
        lib = copy.deepcopy(LIBRARY)
        lib["entries"][1]["id"] = lib["entries"][0]["id"]
        with self.assertRaises(gf.ValidationError):
            gf.validate_library(lib, CONFIG)

    def test_rejects_fact_without_source(self):
        lib = copy.deepcopy(LIBRARY)
        fact = next(e for e in lib["entries"] if e["category"] == "fact")
        fact["sources"] = []
        with self.assertRaises(gf.ValidationError):
            gf.validate_library(lib, CONFIG)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.entries, _ = gf.validate_library(LIBRARY, CONFIG)

    def run_days(self, n, history=None):
        history = history or []
        picks = []
        for i in range(n):
            day = DAY + dt.timedelta(days=i)
            chosen = gf.select_for_date(day, self.entries, history)
            history = gf.record(history, day, chosen)
            picks.append(chosen)
        return picks, history

    def test_no_repeats_within_a_cycle(self):
        per_cat = {c: sum(1 for e in self.entries if e["category"] == c and e["approved"])
                   for c in gf.CATEGORIES}
        n = min(per_cat.values())
        picks, _ = self.run_days(n)
        for c in gf.CATEGORIES:
            ids = [p[c]["id"] for p in picks]
            self.assertEqual(len(ids), len(set(ids)), c)

    def test_same_day_rerun_is_stable(self):
        _, history = self.run_days(1)
        again = gf.select_for_date(DAY, self.entries, history)
        self.assertEqual({c: again[c]["id"] for c in gf.CATEGORIES},
                         {c: history[0][c] for c in gf.CATEGORIES})

    def test_cycle_restarts_without_back_to_back_repeat(self):
        picks, _ = self.run_days(10)
        for a, b in zip(picks, picks[1:]):
            for c in gf.CATEGORIES:
                self.assertNotEqual(a[c]["id"], b[c]["id"])

    def test_unapproved_entries_are_skipped(self):
        entries = copy.deepcopy(self.entries)
        first_phil = next(e for e in entries if e["category"] == "philosophy")
        first_phil["approved"] = False
        chosen = gf.select_for_date(DAY, entries, [])
        self.assertNotEqual(chosen["philosophy"]["id"], first_phil["id"])


class FeedTests(unittest.TestCase):
    def setUp(self):
        entries, _ = gf.validate_library(LIBRARY, CONFIG)
        self.chosen = gf.select_for_date(DAY, entries, [])
        self.xml = gf.build_feed(DAY, self.chosen, CONFIG)

    def test_feed_validates_and_is_ordered(self):
        gf.validate_feed(self.xml, [gf.display_text(self.chosen[c]) for c in CONFIG["category_order"]])
        root = ET.fromstring(self.xml.encode("utf-8"))
        cats = [i.findtext("category") for i in root.iter("item")]
        self.assertEqual(cats, ["philosophy", "reflection", "fact"])

    def test_pubdates_descend_in_display_order(self):
        from email.utils import parsedate_to_datetime
        root = ET.fromstring(self.xml.encode("utf-8"))
        dates = [parsedate_to_datetime(i.findtext("pubDate")) for i in root.iter("item")]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_special_characters_are_escaped(self):
        chosen = copy.deepcopy(self.chosen)
        chosen["fact"]["text"] = 'Less < more & "quotes" > nothing'
        xml = gf.build_feed(DAY, chosen, CONFIG)
        root = ET.fromstring(xml.encode("utf-8"))
        titles = [i.findtext("title") for i in root.iter("item")]
        self.assertEqual(titles[2], 'Less < more & "quotes" > nothing')

    def test_wrong_item_count_rejected(self):
        bad = self.xml.replace("<item>", "<itemx>", 1).replace("</item>", "</itemx>", 1)
        with self.assertRaises(gf.ValidationError):
            gf.validate_feed(bad, [])


if __name__ == "__main__":
    unittest.main()
