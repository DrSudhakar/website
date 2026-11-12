#!/usr/bin/env python3
"""Add / list / remove website content without editing JSON by hand.

  python scripts/manage.py add news          # asks you questions, then writes data/news.json
  python scripts/manage.py add member
  python scripts/manage.py add project | grant | publication | video | talk | alumni
  python scripts/manage.py list member
  python scripts/manage.py remove member     # pick which one to delete
  python scripts/manage.py refresh           # pull new papers, citations, YouTube videos, model lists
  python scripts/manage.py check             # validate everything before you publish

Non-interactive (handy for scripts):  add news --set date=2026-11-01 --set text="Won an award"
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load, save  # noqa: E402

TODAY = date.today().isoformat()
# field = (key, question, default, kind)   kinds: str | list (comma separated) | choice:a/b/c | opt (may be blank)
FORMS = {
    "news": {"file": "news.json", "where": None, "fields": [
        ("date", "Date (YYYY-MM-DD, or YYYY-MM)", TODAY, "str"), ("text", "What happened? (one sentence)", None, "str"), ("link", "Link (optional)", "", "opt")]},
    "member": {"file": "members.json", "where": "current", "fields": [
        ("name", "Full name", None, "str"),
        ("role", "Role", "PhD Student", "choice:PhD Student/MTech Student/BTech Student/Research Intern/Postdoc/Research Associate/Collaborator"),
        ("period", "Period (e.g. 2026–present)", "", "opt"), ("bio", "One-line bio / research interest", "", "opt"),
        ("photo", "Photo path (e.g. assets/img/members/ravi.jpg) — leave blank for initials", "", "opt"),
        ("links.scholar", "Google Scholar URL", "", "opt"), ("links.github", "GitHub URL", "", "opt"), ("links.linkedin", "LinkedIn URL", "", "opt"),
        ("work", "Their work: 'Title | link' items separated by ;", "", "work")]},
    "alumni": {"file": "members.json", "where": "alumni", "fields": [
        ("name", "Full name", None, "str"), ("role", "Role", "Alumnus", "str"), ("period", "Period", "", "opt"), ("bio", "Now at / next step", "", "opt"), ("work", "Their work", "", "work")]},
    "project": {"file": "projects.json", "where": None, "fields": [
        ("title", "Project title", None, "str"), ("status", "Status", "Ongoing", "choice:Ongoing/Under review/Completed/Planned"),
        ("area", "Area (e.g. Affective computing · EEG)", "", "opt"), ("summary", "Two-sentence summary", None, "str"),
        ("people", "People (comma separated)", "", "list"), ("link", "Link (paper, GitHub …)", "", "opt")]},
    "grant": {"file": "grants.json", "where": None, "fields": [
        ("year", "Year", str(date.today().year), "str"), ("title", "Grant title", None, "str"), ("role", "Your role", "PI", "str"),
        ("agency", "Funding agency", None, "str"), ("note", "Amount / note (optional)", "", "opt")]},
    "publication": {"file": "publications_manual.json", "where": None, "fields": [
        ("title", "Title", None, "str"), ("authors", "Authors, comma separated (use your name exactly: Sudhakar Mishra)", None, "list"),
        ("venue", "Venue (journal / conference, with volume/pages)", None, "str"), ("year", "Year", str(date.today().year), "int"),
        ("type", "Type", "journal", "choice:journal/conference/preprint/dataset/inprogress/other"),
        ("status", "Status", "published", "choice:published/under-review/in-progress"),
        ("doi", "DOI (e.g. 10.1109/ACCESS.2023.3266804)", "", "opt"), ("url", "URL (arXiv / publisher)", "", "opt"), ("featured", "Show on the home page? (yes/no)", "no", "bool")]},
    "video": {"file": "videos.json", "where": None, "fields": [
        ("title", "Title", None, "str"), ("url", "Video link (YouTube / Vimeo / Drive …)", None, "str"),
        ("type", "Category", "Lecture", "choice:Lecture/Talk/Seminar/Tutorial/Demo"), ("date", "Date", TODAY, "str"),
        ("course", "Course name (for lectures, optional)", "", "opt"), ("description", "Short description (optional)", "", "opt")]},
    "talk": {"file": "talks.json", "where": None, "fields": [
        ("title", "Talk title", None, "str"), ("date", "Date (YYYY-MM)", TODAY[:7], "str"), ("venue", "Event / venue", None, "str"),
        ("video", "Video link (optional)", "", "opt"), ("slides", "Slides link (optional)", "", "opt")]},
    "vacancy": {"file": "vacancies.json", "where": "openings", "fields": [
        ("id", "Short id (no spaces, e.g. phd-2027)", None, "str"), ("type", "Type", "PhD", "choice:PhD/Summer research intern/Winter research intern/Postdoc/Project staff"),
        ("title", "Title", None, "str"), ("status", "Status", "open", "choice:open/closed"), ("when", "Start / season", "", "opt"), ("deadline", "Deadline (YYYY-MM-DD)", "", "opt"),
        ("topics", "Topics, separated by ;", None, "semi"), ("requirements", "Requirements, separated by ;", "", "semi")]},
}
ALIASES = {"members": "member", "projects": "project", "grants": "grant", "publications": "publication", "videos": "video", "talks": "talk", "vacancies": "vacancy"}


def ask(key, question, default, kind, preset):
    if key in preset:
        raw = preset[key]
    elif preset:                      # non-interactive mode (--set used): fall back to defaults, never prompt
        if default is None:
            sys.exit(f"missing required --set {key}=...")
        raw = default
    else:
        choices = kind.split(":")[1].split("/") if kind.startswith("choice:") else None
        hint = f" [{'/'.join(choices)}]" if choices else ""
        dflt = f" (Enter = {default})" if default not in (None, "") else ""
        while True:
            raw = input(f"{question}{hint}{dflt}: ").strip()
            if not raw and default is not None:
                raw = default
            if raw or kind == "opt" or default == "":
                break
            print("   this one is required")
    if kind == "list":
        return [x.strip() for x in raw.split(",") if x.strip()]
    if kind == "semi":
        return [x.strip() for x in raw.split(";") if x.strip()]
    if kind == "int":
        return int(raw)
    if kind == "bool":
        return raw.lower() in ("y", "yes", "true", "1")
    if kind == "work":
        out = []
        for part in [p for p in raw.split(";") if p.strip()]:
            t, _, l = part.partition("|")
            out.append({"title": t.strip(), **({"link": l.strip()} if l.strip() else {})})
        return out
    return raw


def build(form, preset):
    rec = {}
    for key, q, d, kind in form["fields"]:
        v = ask(key, q, d, kind, preset)
        if v in ("", [], None) and kind in ("opt", "work"):
            continue
        if "." in key:
            a, b = key.split(".")
            rec.setdefault(a, {})[b] = v
        else:
            rec[key] = v
    return rec


def container(doc, form):
    return doc[form["where"]] if form["where"] else doc


def label(rec):
    return rec.get("name") or rec.get("title") or rec.get("text") or str(rec)


def cmd_add(what, preset):
    form = FORMS[what]
    doc = load(form["file"], {} if form["where"] else [])
    rec = build(form, preset)
    if what == "member":
        rec.setdefault("work", [])
    container(doc, form).insert(0, rec) if what in ("news", "publication", "video") else container(doc, form).append(rec)
    save(form["file"], doc)
    print(f"✔ added to data/{form['file']}: {label(rec)}")
    if what == "publication":
        print("  (it will also appear on the Publications page right after the next 'refresh', or run: python scripts/update_publications.py)")


def cmd_list(what):
    for i, rec in enumerate(container(load(FORMS[what]["file"], {} if FORMS[what]["where"] else []), FORMS[what]), 1):
        print(f"{i:3d}. {label(rec)}")


def cmd_remove(what, number):
    form = FORMS[what]
    doc = load(form["file"], {} if form["where"] else [])
    items = container(doc, form)
    cmd_list(what)
    n = number or int(input("Number to remove: "))
    gone = items.pop(n - 1)
    save(form["file"], doc)
    print("✔ removed", label(gone))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["add", "list", "remove", "refresh", "check"])
    ap.add_argument("what", nargs="?")
    ap.add_argument("--set", action="append", default=[], metavar="key=value")
    ap.add_argument("--number", type=int)
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    if a.action == "refresh":
        for s in ("update_publications.py", "update_youtube.py", "update_llm_models.py"):
            print(f"\n== {s}"); subprocess.run([sys.executable, str(here / s)], check=False)
        return 0
    if a.action == "check":
        return subprocess.run([sys.executable, str(here / "validate_data.py")]).returncode
    what = ALIASES.get(a.what, a.what)
    if what not in FORMS:
        ap.error(f"choose one of: {', '.join(FORMS)}")
    preset = dict(kv.split("=", 1) for kv in a.set)
    {"add": lambda: cmd_add(what, preset), "list": lambda: cmd_list(what), "remove": lambda: cmd_remove(what, a.number)}[a.action]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
