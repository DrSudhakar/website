#!/usr/bin/env python3
"""Check every data/*.json file for mistakes a beginner is likely to make (typos, broken commas, bad links, missing images).
Exit code 1 if there are errors; warnings are only printed.  Run:  python scripts/validate_data.py"""
import json
import re
import sys
from pathlib import Path

from _common import DATA, ROOT

errors, warns = [], []
err = lambda m: errors.append(m)
warn = lambda m: warns.append(m)
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def get(name, kind):
    p = DATA / name
    if not p.exists():
        err(f"{name}: file is missing"); return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(f"{name}: not valid JSON — {e.msg} at line {e.lineno}, column {e.colno} (usually a missing or extra comma / quote)"); return None
    if not isinstance(d, kind):
        err(f"{name}: expected {kind.__name__}"); return None
    return d


def need(name, rec, keys, label):
    for k in keys:
        if not rec.get(k):
            err(f"{name}: {label} is missing '{k}'")


def url_ok(name, u, label):
    if u and not re.match(r"^(https?://|mailto:)", u) and not (ROOT / u.split("#")[0].split("?")[0]).exists():
        err(f"{name}: {label} → '{u}' is neither a full http(s) link nor an existing file")


def img_ok(name, path, label):
    if path and not (ROOT / path).exists():
        err(f"{name}: {label} image '{path}' does not exist")


site = get("site.json", dict) or {}
need("site.json", site, ["name", "title", "institute", "photo"], "site")
img_ok("site.json", site.get("photo"), "photo")
if not site.get("email"):
    warn("site.json: 'email' is empty — add it so the Email button and Vacancies 'Apply' buttons appear")
if not site.get("social", {}).get("linkedin"):
    warn("site.json: social.linkedin is empty (add https://www.linkedin.com/in/your-handle)")

for rec in get("news.json", list) or []:
    need("news.json", rec, ["date", "text"], "news item")
    if rec.get("date") and not DATE.match(rec["date"]):
        err(f"news.json: date '{rec['date']}' must look like 2026-11-05, 2026-11 or 2026")
    url_ok("news.json", rec.get("link"), "link")

m = get("members.json", dict) or {}
for grp in ("current", "alumni"):
    for rec in m.get(grp, []):
        need("members.json", rec, ["name"], f"{grp} member")
        img_ok("members.json", rec.get("photo"), rec.get("name", "?"))
        for k, u in (rec.get("links") or {}).items():
            url_ok("members.json", u, f"{rec.get('name')} {k}")

for rec in get("projects.json", list) or []:
    need("projects.json", rec, ["title", "summary"], "project"); url_ok("projects.json", rec.get("link"), rec.get("title", "project"))
for rec in get("grants.json", list) or []:
    need("grants.json", rec, ["year", "title"], "grant")
for name in ("publications_manual.json", "publications.json"):
    seen = set()
    for rec in get(name, list) or []:
        need(name, rec, ["title", "authors", "year"], f"publication '{str(rec.get('title'))[:40]}'")
        if not isinstance(rec.get("authors"), list):
            err(f"{name}: authors of '{str(rec.get('title'))[:40]}' must be a list: [\"A\", \"B\"]")
        if rec.get("type") not in (None, "journal", "conference", "preprint", "dataset", "inprogress", "other"):
            err(f"{name}: unknown type '{rec['type']}'")
        t = re.sub(r"\W+", " ", str(rec.get("title")).lower()).strip()
        if t in seen:
            warn(f"{name}: duplicate title '{rec.get('title')[:50]}'")
        seen.add(t)
for rec in get("videos.json", list) or []:
    need("videos.json", rec, ["title", "url"], "video"); url_ok("videos.json", rec.get("url"), rec.get("title", "video"))
for rec in get("talks.json", list) or []:
    need("talks.json", rec, ["title", "date"], "talk")
v = get("vacancies.json", dict) or {}
for rec in v.get("openings", []):
    need("vacancies.json", rec, ["id", "title", "type"], "opening")
    if rec.get("status") not in ("open", "closed"):
        err(f"vacancies.json: '{rec.get('title')}' status must be \"open\" or \"closed\"")
t = get("teaching.json", dict) or {}
for rec in t.get("current", []):
    need("teaching.json", rec, ["title"], "course")
    for mat in rec.get("materials", []):
        url_ok("teaching.json", mat.get("url"), mat.get("label", "material"))
for name in ("metrics.json", "youtube.json", "llm_models.json", "eeg_models.json", "eeg_candidates.json", "publications_hidden.json", "llm_models_pinned.json"):
    if (DATA / name).exists():
        get(name, (dict, list))

for w in warns:
    print("WARNING:", w)
for e in errors:
    print("ERROR:  ", e)
print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
sys.exit(1 if errors else 0)
