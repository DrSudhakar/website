#!/usr/bin/env python3
"""Refresh data/publications.json and data/metrics.json.

Sources (in order of trust):
  1. data/publications_manual.json  – your curated list (always kept, never overwritten)
  2. OpenAlex (free API, reliable)  – adds new papers automatically, and citation counts
  3. Google Scholar profile page    – citation / h-index / i10 metrics, per-year citations, and papers missing elsewhere.
     Scholar sometimes blocks cloud servers (GitHub Actions); if so the previous metrics are simply kept.
Papers listed in data/publications_hidden.json (by title) are never shown (use it for wrong matches).
Run:  python scripts/update_publications.py
"""
import html
import re
import sys
import urllib.parse
from datetime import date
from difflib import SequenceMatcher

from _common import http_get, http_json, load, norm_title, save


def scholar(user):
    url = f"https://scholar.google.com/citations?user={user}&hl=en&cstart=0&pagesize=100&sortby=pubdate"
    code, page = http_get(url, timeout=40)
    if code != 200 or "gsc_rsb_st" not in page:
        print(f"! Scholar not reachable (HTTP {code}) – keeping previous metrics")
        return None
    vals = [int(v) for v in re.findall(r'gsc_rsb_std">(\d+)', page)]
    if len(vals) < 6:
        return None
    years = [int(y) for y in re.findall(r'class="gsc_g_t"[^>]*>(\d{4})<', page)]
    counts = [int(c) for c in re.findall(r'class="gsc_g_al">(\d+)<', page)]
    per_year = dict(zip(map(str, years), counts)) if len(years) == len(counts) else {}
    papers = []
    for row in re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page, flags=re.S):
        t = re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', row, flags=re.S)
        grays = re.findall(r'class="gs_gray">(.*?)</div>', row, flags=re.S)
        c = re.search(r'class="gsc_a_ac[^"]*"[^>]*>(\d*)<', row)
        y = re.search(r'class="gsc_a_h[^"]*"[^>]*>(\d{4})<', row)
        if t:
            clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
            papers.append({"title": clean(t.group(1)), "authors": [a.strip() for a in clean(grays[0]).split(",")] if grays else [],
                           "venue": clean(grays[1]) if len(grays) > 1 else "", "citations": int(c.group(1)) if c and c.group(1) else 0,
                           "year": int(y.group(1)) if y else None})
    return {"metrics": {"citations": vals[0], "citations_recent": vals[1], "h_index": vals[2], "i10_index": vals[4], "per_year": per_year}, "papers": papers}


def openalex(author_id):
    out, cursor = [], "*"
    for _ in range(5):
        url = ("https://api.openalex.org/works?filter=author.id:" + author_id + "&per-page=100&cursor=" + urllib.parse.quote(cursor) +
               "&select=id,title,publication_year,doi,type,authorships,primary_location,cited_by_count")
        d = http_json(url)
        if not d:
            print("! OpenAlex not reachable")
            break
        out += d.get("results", [])
        cursor = (d.get("meta") or {}).get("next_cursor")
        if not cursor or not d.get("results"):
            break
    return out


TYPE_MAP = {"article": "journal", "proceedings-article": "conference", "preprint": "preprint", "dataset": "dataset", "book-chapter": "other", "book": "other"}


def from_openalex(w):
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {}).get("display_name") or ""
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    typ = TYPE_MAP.get(w.get("type"), "other")
    if "arxiv" in src.lower():
        typ = "preprint"
    return {"title": (w.get("title") or "").strip(), "authors": [a["author"]["display_name"] for a in w.get("authorships", [])], "venue": src,
            "year": w.get("publication_year"), "type": typ, "status": "published", "doi": doi, "url": "" if doi else (loc.get("landing_page_url") or ""),
            "featured": False, "citations": w.get("cited_by_count", 0), "auto": True}


def similar(a, b):
    if a == b or SequenceMatcher(None, a, b).ratio() >= 0.92:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 20 and long_.startswith(short)


def main():
    site = load("site.json", {})
    ids = site.get("ids", {})
    manual = load("publications_manual.json", [])
    hidden = {norm_title(t) for t in load("publications_hidden.json", [])}
    sch = scholar(ids["scholar_user"]) if ids.get("scholar_user") else None
    oa = openalex(ids["openalex_author"]) if ids.get("openalex_author") else []

    # ---- metrics
    old = load("metrics.json", {})
    if sch:
        m = dict(sch["metrics"], updated=date.today().isoformat(), source="google-scholar")
        save("metrics.json", m)
        print(f"metrics: {m['citations']} citations, h={m['h_index']}, i10={m['i10_index']}")
    else:
        if oa and not old:
            save("metrics.json", {"updated": date.today().isoformat(), "source": "openalex", "citations": sum(w.get("cited_by_count", 0) for w in oa), "citations_recent": 0, "h_index": 0, "i10_index": 0, "per_year": {}})
        print("metrics: unchanged")

    # ---- publications
    cite_lookup = {}
    for p in (sch["papers"] if sch else []):
        cite_lookup[norm_title(p["title"])] = p["citations"]
    for w in oa:
        k = norm_title(w.get("title"))
        cite_lookup.setdefault(k, w.get("cited_by_count", 0))
    pubs = [dict(p) for p in manual if norm_title(p["title"]) not in hidden]
    keys = [norm_title(p["title"]) for p in pubs]
    for p, k in zip(pubs, keys):
        best = max(((c, v) for c, v in cite_lookup.items() if similar(k, c)), key=lambda cv: cv[1], default=None)
        if best:
            p["citations"] = best[1]
    # ---- automatic additions.  OpenAlex sometimes merges *other people with the same name* into one profile
    # (e.g. unrelated poultry-genetics papers), so OpenAlex alone is NOT trusted to add papers.
    #   • Papers on your Google Scholar profile are trusted if dated >= auto_add_min_year (site.json -> ids); OpenAlex only enriches them (DOI, authors, venue, type).
    #   • OpenAlex-only papers are added only if they share a co-author with your curated list (a corroboration check);
    #     otherwise they are just reported in the log so you can add them by hand.
    new, skipped = [], []
    oa_by_key = {norm_title(w.get("title")): from_openalex(w) for w in oa}
    me = norm_title(site.get("name", ""))
    known_co = {norm_title(a) for p in manual for a in p.get("authors", [])} - {me, ""}
    min_year = int(ids.get("auto_add_min_year", 2014))     # your first paper is from 2014 – older "matches" are other people
    def add(c, why):
        k = norm_title(c["title"])
        if not k or k in hidden or any(similar(k, h) for h in hidden) or any(similar(k, e) for e in keys):
            return
        if not c.get("year") or int(c["year"]) < min_year:
            skipped.append(c)       # reported in the log, never published automatically
            return
        c["auto"] = True
        pubs.append(c); keys.append(k); new.append(c)
    for sp in (sch["papers"] if sch else []):
        k = norm_title(sp["title"])
        match = next((v for ok, v in oa_by_key.items() if similar(k, ok)), None)
        c = dict(match) if match else dict(sp, type="other", status="published", doi="", url="", featured=False)
        c["citations"] = sp["citations"]
        if match and not c.get("year"):
            c["year"] = sp["year"]
        add(c, "scholar")
    for k, c in oa_by_key.items():
        if any(similar(k, e) for e in keys) or k in hidden:
            continue
        coauthors = {norm_title(a) for a in c["authors"]} - {me}
        if not sch and coauthors & known_co:
            add(c, "openalex+coauthor")
        elif not any(similar(k, e) for e in keys):
            skipped.append(c)
    for i, p in enumerate(pubs):
        p.setdefault("id", f"a{i:03d}")
        if not p.get("citations"):
            p.pop("citations", None)
    save("publications.json", pubs)
    print(f"publications: {len(pubs)} total, {len(new)} newly added automatically")
    for n in new:
        print(f"   + {n['year']}  {n['title'][:90]}")
    if skipped:
        print(f"   {len(skipped)} OpenAlex-only paper(s) NOT added (not on your Scholar profile / no known co-author):")
        for n in skipped[:12]:
            print(f"   ? {n['year']}  {n['title'][:90]}")
    if new:
        print("   (tip: copy a good entry into data/publications_manual.json to fix its type/venue; add wrong ones to publications_hidden.json)")


if __name__ == "__main__":
    sys.exit(main())
