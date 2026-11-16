#!/usr/bin/env python3
"""Write content/CONTENT.md: every entry in display order, with attribution and sources.

    python scripts/export_content.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
lib = json.loads((ROOT / "content" / "library.json").read_text(encoding="utf-8"))
entries = [e for e in lib["entries"] if e["approved"]]
by_cat = {c: [e for e in entries if e["category"] == c] for c in ("philosophy", "reflection", "fact")}
days = max(len(v) for v in by_cat.values())

def shown(e):
    a = e.get("display_attribution")
    return f"{e['text']} — {a}" if a else e["text"]

out = ["# Daily Perspectives — content library", "",
       f"{len(entries)} approved entries. Days run in this order, then the cycle repeats.", ""]
for d in range(days):
    out.append(f"## Day {d + 1}")
    for cat in ("philosophy", "reflection", "fact"):
        if d >= len(by_cat[cat]):
            continue
        e = by_cat[cat][d]
        lang = " (ES)" if e["lang"] == "es" else ""
        out.append(f"- **{cat.title()}{lang}:** {shown(e)}  ")
        bits = []
        if cat == "philosophy":
            bits.append(f"{e['kind'].replace('_', ' ')} · {e['author']}, {e['work']}")
            if e.get("translation"):
                bits.append(f"translation: {e['translation']}")
        if cat == "fact" and e.get("notes"):
            bits.append(e["notes"])
        srcs = e.get("sources") or ([e["link"]] if e.get("link") else [])
        if srcs:
            bits.append("source: " + ", ".join(srcs))
        if bits:
            out.append("  _" + " · ".join(bits) + "_")
    out.append("")
(ROOT / "content" / "CONTENT.md").write_text("\n".join(out), encoding="utf-8")
print(f"Wrote content/CONTENT.md ({days} days)")
