"""Tiny helpers shared by the update scripts (standard library only, so nothing needs installing)."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def http_get(url, headers=None, timeout=30, retries=2):
    h = {"User-Agent": UA, "Accept-Language": "en"}
    h.update(headers or {})
    last = None
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = (e.code, "")
            if e.code in (404, 403, 401):
                return last
        except Exception as e:  # network hiccup
            last = (0, str(e))
        time.sleep(1.5 * (i + 1))
    return last


def http_json(url, headers=None, **kw):
    code, body = http_get(url, headers, **kw)
    if code != 200:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
