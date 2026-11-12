#!/usr/bin/env python3
"""Discover new open-source EEG models on Hugging Face and add them to data/eeg_candidates.json.

Search terms are in QUERIES. Candidates are only *listed* here; scripts/test_eeg_models.py then actually tries to load and run each one
and writes the verdict into data/eeg_models.json — only models that pass are offered on the website.
Run:  python scripts/update_eeg_models.py"""
import sys
from datetime import date

from _common import http_json, load, save

QUERIES = ["eeg emotion", "eeg foundation model", "eeg", "braindecode eeg", "affective eeg"]
MIN_DOWNLOADS = 50
MAX_NEW_PER_RUN = 12


def main():
    old = load("eeg_candidates.json", {"candidates": []})
    seen = {c["id"] for c in old["candidates"]}
    found = {}
    for q in QUERIES:
        d = http_json("https://huggingface.co/api/models?search=" + q.replace(" ", "+") + "&sort=downloads&limit=40&expand[]=downloads&expand[]=likes&expand[]=tags&expand[]=library_name&expand[]=pipeline_tag&expand[]=gated")
        for m in d or []:
            tags = [t.lower() for t in m.get("tags", [])]
            if m.get("gated") or m.get("downloads", 0) < MIN_DOWNLOADS or "eeg" not in " ".join(tags + [m["id"].lower()]):
                continue
            found[m["id"]] = {"id": m["id"], "downloads": m.get("downloads", 0), "likes": m.get("likes", 0), "library": m.get("library_name"), "tags": m.get("tags", [])[:15]}
    new = [v for k, v in sorted(found.items(), key=lambda kv: -kv[1]["downloads"]) if k not in seen][:MAX_NEW_PER_RUN]
    for n in new:
        n["added"] = date.today().isoformat()
    cands = old["candidates"] + new
    for c in cands:
        if c["id"] in found:
            c["downloads"] = found[c["id"]]["downloads"]
    save("eeg_candidates.json", {"updated": date.today().isoformat(), "candidates": cands})
    print(f"eeg candidates: {len(cands)} known, {len(new)} new")
    for n in new:
        print("   +", n["id"], n["downloads"])


if __name__ == "__main__":
    sys.exit(main())
