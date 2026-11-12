#!/usr/bin/env python3
"""Refresh data/llm_models.json — the list of open-source chat LLMs offered in the empathy checker.

Takes the currently trending text-generation models on Hugging Face that at least one inference provider serves LIVE
(so the empathy checker can actually call them), merges them with the previous list (keeping the date each was first seen),
and always keeps the names in data/llm_models_pinned.json (your favourites).
Run:  python scripts/update_llm_models.py"""
import sys
from datetime import date

from _common import http_json, load, save

URL = ("https://huggingface.co/api/models?pipeline_tag=text-generation&inference_provider=all&sort=trendingScore&limit=100"
       "&expand[]=downloads&expand[]=likes&expand[]=tags&expand[]=inferenceProviderMapping&expand[]=safetensors&expand[]=gated&expand[]=trendingScore")
MAX_MODELS = 40


def main():
    d = http_json(URL, timeout=60)
    if not d:
        print("! Hugging Face not reachable – keeping previous list"); return 0
    today = date.today().isoformat()
    old = {m["id"]: m for m in (load("llm_models.json", {}) or {}).get("models", [])}
    pinned = load("llm_models_pinned.json", [])
    fresh = []
    for m in d:
        live = [p["provider"] for p in m.get("inferenceProviderMapping", []) if p.get("status") == "live" and p.get("task") in ("conversational", "text-generation")]
        if not live or "conversational" not in [p.get("task") for p in m.get("inferenceProviderMapping", [])]:
            continue
        params = (m.get("safetensors") or {}).get("total")
        fresh.append({"id": m["id"], "provider": "hf", "downloads": m.get("downloads", 0), "likes": m.get("likes", 0), "trending": m.get("trendingScore", 0),
                      "params_b": round(params / 1e9, 1) if params else None, "gated": bool(m.get("gated")), "serving": live[:3], "added": old.get(m["id"], {}).get("added", today)})
        if len(fresh) >= MAX_MODELS:
            break
    ids = {m["id"] for m in fresh}
    for pid in pinned:                               # pinned favourites stay even if not trending
        if pid not in ids:
            fresh.append(dict(old.get(pid, {"id": pid, "provider": "hf", "added": today}), pinned=True))
    new = [m["id"] for m in fresh if m["added"] == today and m["id"] not in old]
    save("llm_models.json", {"updated": today, "source": "huggingface.co trending text-generation models with a live inference provider", "models": fresh})
    print(f"llm models: {len(fresh)} listed, {len(new)} new")
    for n in new[:10]:
        print("   +", n)


if __name__ == "__main__":
    sys.exit(main())
