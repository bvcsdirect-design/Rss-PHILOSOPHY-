#!/usr/bin/env python3
"""Daily Perspectives: select today's three entries and write an RSS 2.0 feed.

Standard library only. Run from the repository root:

    python scripts/generate_feed.py              # publish today's set
    python scripts/generate_feed.py --check      # validate library only
    python scripts/generate_feed.py --preview 7  # show the next 7 days, change nothing
    python scripts/generate_feed.py --date 2026-11-20   # pretend it is that date

Selection rules
  * "Today" is the calendar date in the configured time zone (America/Chicago),
    so daylight saving time never matters.
  * If today already appears in state/history.json, the same three entries are
    reused. Re-running (or a second scheduled run) can never change the day's set.
  * Otherwise, each category gets the approved entry shown the fewest times,
    ties broken by library order. New batches appended to the library are
    therefore shown next, and nothing repeats until every entry has appeared.
    When everything has been shown, the cycle starts over (fallback policy:
    repeat verified content, never invent).
  * Nothing is written unless the library and the generated feed both validate,
    so a failure leaves the last good feed online.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
LIBRARY_PATH = ROOT / "content" / "library.json"
HISTORY_PATH = ROOT / "state" / "history.json"
SITE_DIR = ROOT / "site"

CATEGORIES = ("philosophy", "reflection", "fact")
LANGS = {"en", "es"}
KINDS = {
    "philosophy": {"verified_quote", "verified_translation", "attributed_summary"},
    "reflection": {"original_question"},
    "fact": {"verified_fact"},
}
ATOM_NS = "http://www.w3.org/2005/Atom"


class ValidationError(Exception):
    pass


# ---------------------------------------------------------------- loading

def load_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise ValidationError(f"Missing file: {path.relative_to(ROOT)}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def display_text(entry: dict) -> str:
    text = entry["text"].strip()
    attribution = entry.get("display_attribution")
    return f"{text} — {attribution}" if attribution else text


# ---------------------------------------------------------------- validation

def validate_library(library: dict, config: dict) -> tuple[list[dict], list[str]]:
    """Return (entries, warnings). Raise ValidationError on any hard problem."""
    errors: list[str] = []
    warnings: list[str] = []
    entries = library.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("library.json has no entries list")

    hard_max = config["length"]["hard_max"]
    soft_max = config["length"]["display_soft_max"]
    targets = config["length"]["targets"]
    seen_ids: set[str] = set()
    seen_text: set[str] = set()

    for i, e in enumerate(entries):
        where = f"entry #{i + 1} ({e.get('id', 'no id')})"
        for field in ("id", "category", "text", "lang", "kind", "approved"):
            if field not in e:
                errors.append(f"{where}: missing '{field}'")
        if errors and errors[-1].startswith(where):
            continue

        if e["id"] in seen_ids:
            errors.append(f"{where}: duplicate id")
        seen_ids.add(e["id"])

        cat = e["category"]
        if cat not in CATEGORIES:
            errors.append(f"{where}: unknown category '{cat}'")
            continue
        if e["kind"] not in KINDS[cat]:
            errors.append(f"{where}: kind '{e['kind']}' not allowed for {cat}")
        if e["lang"] not in LANGS:
            errors.append(f"{where}: lang must be one of {sorted(LANGS)}")
        if not isinstance(e["approved"], bool):
            errors.append(f"{where}: 'approved' must be true or false")

        text = e["text"]
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{where}: empty text")
            continue
        if "\n" in text or "\r" in text:
            errors.append(f"{where}: text must be a single line")
        norm = " ".join(text.lower().split())
        if norm in seen_text:
            errors.append(f"{where}: duplicate text")
        seen_text.add(norm)

        if cat in ("philosophy", "fact") and not e.get("sources"):
            errors.append(f"{where}: {cat} entries need at least one source")
        if cat == "philosophy" and not e.get("author"):
            errors.append(f"{where}: philosophy entries need an author")

        shown = display_text(e)
        n = len(shown)
        if n > hard_max:
            errors.append(f"{where}: {n} characters exceeds hard max {hard_max}")
        elif n > soft_max:
            warnings.append(f"{where}: {n} chars, above display_soft_max {soft_max}")
        lo, hi = targets[cat]
        if not lo <= n <= hi:
            warnings.append(f"{where}: {n} chars, outside {cat} target {lo}-{hi}")

    if not errors:
        for cat in CATEGORIES:
            if not any(e["category"] == cat and e["approved"] for e in entries):
                errors.append(f"no approved entries in category '{cat}'")

    if errors:
        raise ValidationError("Library problems:\n  - " + "\n  - ".join(errors))
    return entries, warnings


def validate_feed(xml_text: str, expected_titles: list[str]) -> None:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        raise ValidationError(f"Generated XML does not parse: {exc}") from exc
    if root.tag != "rss" or root.get("version") != "2.0":
        raise ValidationError("Root element must be <rss version=\"2.0\">")
    channel = root.find("channel")
    if channel is None or not (channel.findtext("title") or "").strip():
        raise ValidationError("Channel or channel title missing")
    items = channel.findall("item")
    if len(items) != 3:
        raise ValidationError(f"Feed must have exactly 3 items, found {len(items)}")
    titles = [(it.findtext("title") or "").strip() for it in items]
    if any(not t for t in titles):
        raise ValidationError("Empty item title")
    if titles != expected_titles:
        raise ValidationError("Item order does not match philosophy, reflection, fact")
    guids = [it.findtext("guid") for it in items]
    if len(set(guids)) != 3 or not all(guids):
        raise ValidationError("Item GUIDs missing or not unique")


# ---------------------------------------------------------------- selection

def local_today(config: dict, override: str | None = None) -> dt.date:
    if override:
        return dt.date.fromisoformat(override)
    return dt.datetime.now(ZoneInfo(config["timezone"])).date()


def show_counts(history: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for day in history:
        for cat in CATEGORIES:
            eid = day.get(cat)
            if eid:
                counts[eid] = counts.get(eid, 0) + 1
    return counts


def select_for_date(day: dt.date, entries: list[dict], history: list[dict]) -> dict[str, dict]:
    by_id = {e["id"]: e for e in entries}
    iso = day.isoformat()

    existing = next((h for h in history if h.get("date") == iso), None)
    if existing and all(
        existing.get(c) in by_id and by_id[existing[c]]["approved"] for c in CATEGORIES
    ):
        return {c: by_id[existing[c]] for c in CATEGORIES}

    prior = [h for h in history if h.get("date", "") < iso]
    counts = show_counts(prior)
    last = prior[-1] if prior else {}
    chosen = {}
    for cat in CATEGORIES:
        pool = [(i, e) for i, e in enumerate(entries) if e["category"] == cat and e["approved"]]
        # Prefer not to repeat yesterday's entry even when a cycle restarts.
        fresh = [p for p in pool if p[1]["id"] != last.get(cat)] or pool
        _, pick = min(fresh, key=lambda p: (counts.get(p[1]["id"], 0), p[0]))
        chosen[cat] = pick
    return chosen


def record(history: list[dict], day: dt.date, chosen: dict[str, dict]) -> list[dict]:
    iso = day.isoformat()
    row = {"date": iso, **{c: chosen[c]["id"] for c in CATEGORIES}}
    kept = [h for h in history if h.get("date") != iso]
    kept.append(row)
    kept.sort(key=lambda h: h["date"])
    return kept


# ---------------------------------------------------------------- feed

def build_feed(day: dt.date, chosen: dict[str, dict], config: dict) -> str:
    tz = ZoneInfo(config["timezone"])
    base = dt.datetime.combine(day, dt.time(config["publish_hour_local"], 0), tz)
    site = config["site_url"].rstrip("/") + "/"
    feed_url = config.get("feed_url") or site + config["feed_filename"]

    ET.register_namespace("atom", ATOM_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = config["channel_title"]
    ET.SubElement(ch, "link").text = site
    ET.SubElement(ch, "description").text = config["channel_description"]
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(base)
    ET.SubElement(ch, "ttl").text = "60"
    ET.SubElement(ch, f"{{{ATOM_NS}}}link",
                  {"href": feed_url, "rel": "self", "type": "application/rss+xml"})

    # Philosophy gets the newest timestamp, fact the oldest, so document order
    # and newest-first sorting give the same order.
    for offset, cat in enumerate(config["category_order"]):
        e = chosen[cat]
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = display_text(e)
        ET.SubElement(item, "link").text = e.get("link") or site
        ET.SubElement(item, "description").text = describe(e)
        ET.SubElement(item, "category").text = cat
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = f"{day.isoformat()}-{e['id']}"
        ET.SubElement(item, "pubDate").text = format_datetime(base - dt.timedelta(minutes=offset))

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def describe(e: dict) -> str:
    cat = e["category"]
    if cat == "philosophy":
        label = {"verified_quote": "Quotation", "verified_translation": "Translation",
                 "attributed_summary": "Summary"}[e["kind"]]
        parts = [f"{label}. {e['author']}, {e.get('work', '')}".rstrip(", ")]
        if e.get("translation"):
            parts.append(f"Translation: {e['translation']}")
        return ". ".join(parts)
    if cat == "fact":
        return "Source: " + e["sources"][0]
    return "An original question for reflection."


def write_index(day: dt.date, chosen: dict[str, dict], config: dict) -> str:
    from html import escape
    rows = "\n".join(
        f"<li><b>{escape(c.title())}:</b> {escape(display_text(chosen[c]))}</li>"
        for c in config["category_order"]
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(config['channel_title'])}</title></head>
<body style="font-family:system-ui;max-width:40rem;margin:2rem auto;padding:0 1rem">
<h1>{escape(config['channel_title'])}</h1>
<p>Set for {day.isoformat()} ({escape(config['timezone'])}).</p>
<ul>{rows}</ul>
<p><a href="{escape(config['feed_filename'])}">RSS feed</a></p>
</body></html>
"""


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="YYYY-MM-DD to generate for (default: today, local)")
    ap.add_argument("--check", action="store_true", help="validate the library and exit")
    ap.add_argument("--preview", type=int, metavar="DAYS", help="print upcoming days, write nothing")
    args = ap.parse_args(argv)

    try:
        config = load_json(CONFIG_PATH)
        if os.environ.get("SITE_URL"):  # set by the workflow from GitHub Pages
            config["site_url"] = os.environ["SITE_URL"]
        entries, warnings = validate_library(load_json(LIBRARY_PATH), config)
        for w in warnings:
            print(f"warning: {w}")
        if args.check:
            print(f"OK: {len(entries)} entries valid.")
            return 0

        history = load_json(HISTORY_PATH, default=[])
        today = local_today(config, args.date)

        if args.preview:
            sim = list(history)
            for n in range(args.preview):
                day = today + dt.timedelta(days=n)
                chosen = select_for_date(day, entries, sim)
                sim = record(sim, day, chosen)
                print(day.isoformat())
                for c in config["category_order"]:
                    t = display_text(chosen[c])
                    print(f"  {c:<10} ({len(t):>3}) {t}")
            return 0

        chosen = select_for_date(today, entries, history)
        feed = build_feed(today, chosen, config)
        validate_feed(feed, [display_text(chosen[c]) for c in config["category_order"]])

        atomic_write(SITE_DIR / config["feed_filename"], feed)
        atomic_write(SITE_DIR / "index.html", write_index(today, chosen, config))
        atomic_write(HISTORY_PATH, json.dumps(record(history, today, chosen), indent=2) + "\n")
        print(f"Published {today.isoformat()}:")
        for c in config["category_order"]:
            print(f"  {c}: {chosen[c]['id']}  {display_text(chosen[c])}")
        return 0
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Nothing was written; the previous feed stays online.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
