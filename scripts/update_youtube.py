#!/usr/bin/env python3
"""Refresh data/youtube.json with the latest uploads of your channel (no API key needed).
Tries the channel's public RSS feed first, then falls back to reading the channel's /videos page.
Run:  python scripts/update_youtube.py"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from _common import http_get, load, save


def rss(channel_id):
    code, body = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    if code != 200:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    out = []
    for e in ET.fromstring(body).findall("a:entry", ns):
        out.append({"id": e.find("yt:videoId", ns).text, "title": e.find("a:title", ns).text, "published": e.find("a:published", ns).text})
    return out


def scrape(handle):
    code, page = http_get(f"https://www.youtube.com/@{handle}/videos")
    if code != 200:
        return None
    out, seen = [], set()
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}\]', page, flags=re.S):
        vid, title = m.group(1), json.loads('"' + m.group(2) + '"')
        if vid not in seen:
            seen.add(vid); out.append({"id": vid, "title": title, "published": ""})
    return out


def main():
    ids = load("site.json", {}).get("ids", {})
    vids = rss(ids["youtube_channel_id"]) if ids.get("youtube_channel_id") else None
    how = "rss"
    if vids is None:
        vids, how = scrape(ids.get("youtube_handle", "")), "page"
    if vids is None:
        print("! YouTube not reachable – keeping previous list"); return 0
    old = load("youtube.json", {"videos": []})
    known = {v["id"]: v for v in old.get("videos", [])}
    for v in vids:                      # keep publish dates we learned earlier
        if not v["published"] and v["id"] in known:
            v["published"] = known[v["id"]].get("published", "")
    merged = {v["id"]: v for v in old.get("videos", [])}   # never lose a video that is still public but fell off the feed
    merged.update({v["id"]: v for v in vids})
    out = sorted(merged.values(), key=lambda v: v.get("published", ""), reverse=True)
    save("youtube.json", {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "channel": load("site.json", {}).get("social", {}).get("youtube", ""), "videos": out})
    print(f"youtube ({how}): {len(out)} videos")
    for v in out[:5]:
        print("   ", v["id"], v["title"][:70])


if __name__ == "__main__":
    sys.exit(main())
