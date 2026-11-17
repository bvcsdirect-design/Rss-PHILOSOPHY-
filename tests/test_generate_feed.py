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


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.entries, _ = gf.validate_library(LIBRARY, CONFIG)
        self.cycle = CONFIG["widget_cycle_days"]

    def items(self, today, history=None):
        xml = gf.build_schedule(today, self.entries, history or [], CONFIG)
        return ET.fromstring(xml.encode("utf-8")).findall("channel/item")

    def kwgt_block(self, day):
        # Same arithmetic the widget does: (yyyy*366 + D) - floor(.../cycle)*cycle
        n = int(day.strftime("%Y")) * 366 + int(day.strftime("%j"))
        return n - (n // self.cycle) * self.cycle

    def test_has_full_cycle_in_category_order(self):
        items = self.items(DAY)
        self.assertEqual(len(items), 3 * self.cycle)
        cats = [i.findtext("category") for i in items]
        self.assertEqual(cats, ["philosophy", "reflection", "fact"] * self.cycle)

    def test_each_day_reads_its_own_set(self):
        history = []
        expected = {}
        for n in range(self.cycle):
            d = DAY + dt.timedelta(days=n)
            chosen = gf.select_for_date(d, self.entries, history)
            history = gf.record(history, d, chosen)
            expected[d] = gf.display_text(chosen["philosophy"])
        items = self.items(DAY)
        for d, title in expected.items():
            self.assertEqual(items[3 * self.kwgt_block(d)].findtext("title"), title, d)

    def test_year_end_window_has_no_gaps(self):
        items = self.items(dt.date(2026, 12, 20))
        self.assertTrue(all((i.findtext("title") or "").strip() for i in items))
        d = dt.date(2027, 1, 2)
        self.assertTrue(items[3 * self.kwgt_block(d)].findtext("title"))

    def test_late_run_still_matches_today(self):
        # A run made yesterday must already contain today's set in today's block.
        yesterday = DAY - dt.timedelta(days=1)
        hist = gf.record([], yesterday, gf.select_for_date(yesterday, self.entries, []))
        today_set = gf.select_for_date(DAY, self.entries, hist)
        items = self.items(yesterday)
        self.assertEqual(items[3 * self.kwgt_block(DAY)].findtext("title"),
                         gf.display_text(today_set["philosophy"]))
