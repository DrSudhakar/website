"""Pay-per-minute access for the heavy demos (LLM empathy checker, EEG lab).

Rules (all numbers can be changed in functions/.env, see .env.example):
  * Every signed-in user gets FREE_MINUTES_PER_USER free minutes per calendar month (IST).
  * All free use on the site shares one monthly pool, FREE_POOL_MINUTES. Once it is used up nobody gets
    free minutes until the 1st of next month; paid minutes still work.
  * After that, minutes cost PRICE_PER_MINUTE_INR. Users pay to the owner's UPI QR code and submit the
    transaction reference; an admin (ADMIN_EMAILS) approves it and the minutes are credited.
  * Nobody can use more than DAILY_CAP_MINUTES per day, and only one run per user at a time.
  * Usage = wall-clock seconds a request spends on the server. Free minutes are used first.

Firestore layout (clients cannot read or write it; see firestore.rules):
  billing_users/{uid}       month, free_used_s, day, day_used_s, paid_balance_s, active_until, ...
  billing_pool/{YYYY-MM}    free_used_s
  billing_requests/{id}     uid, email, minutes, amount_inr, upi_ref, status, created, ...
"""
from __future__ import annotations

import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
LOCK_SECONDS = 360                      # a run can take at most 300 s (function timeout) + margin
MAX_PENDING_PER_USER = 3
REF_RE = re.compile(r"^[A-Za-z0-9]{6,40}$")


def _num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


class Settings:
    def __init__(self):
        self.free_s = int(_num("FREE_MINUTES_PER_USER", 5) * 60)
        self.pool_s = int(_num("FREE_POOL_MINUTES", 900) * 60)
        self.price = _num("PRICE_PER_MINUTE_INR", 1)
        self.cap_s = int(_num("DAILY_CAP_MINUTES", 120) * 60)
        self.min_start_s = int(_num("MIN_START_SECONDS", 30))
        self.max_buy_min = int(_num("MAX_PURCHASE_MINUTES", 600))
        self.admins = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


class Denied(Exception):
    def __init__(self, code: str, message: str, http: int = 402, status: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.http, self.status = code, message, http, status


def is_admin(email: str) -> bool:
    return bool(email) and email.lower() in Settings().admins


# ---------------------------------------------------------------- dates (India Standard Time)
def _keys(now: float) -> tuple[str, str]:
    d = datetime.fromtimestamp(now, IST)
    return d.strftime("%Y-%m"), d.strftime("%Y-%m-%d")


def next_month_start(now: float) -> str:
    d = datetime.fromtimestamp(now, IST)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return f"{y:04d}-{m:02d}-01"


def tomorrow(now: float) -> str:
    return (datetime.fromtimestamp(now, IST).date() + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------- pure accounting
def _fresh_user(doc: dict | None, email: str | None, now: float) -> dict:
    month, day = _keys(now)
    u = dict(doc or {})
    u.setdefault("paid_balance_s", 0)
    u.setdefault("total_used_s", 0)
    u.setdefault("active_until", 0)
    u.setdefault("created", now)
    if email:
        u["email"] = email
    if u.get("month") != month:
        u["month"], u["free_used_s"] = month, 0
    if u.get("day") != day:
        u["day"], u["day_used_s"] = day, 0
    return u


def summary(u: dict | None, pool: dict | None, now: float, s: Settings) -> dict:
    pool_left = max(0, s.pool_s - int((pool or {}).get("free_used_s", 0)))
    out = {"price_per_minute": s.price, "currency": "INR", "free_minutes_per_user": s.free_s // 60,
           "daily_cap_minutes": s.cap_s // 60, "max_purchase_minutes": s.max_buy_min,
           "pool_exhausted": pool_left < s.min_start_s, "free_resets_on": next_month_start(now), "day_resets_on": tomorrow(now)}
    if u is None:
        return out
    free_user_left = max(0, s.free_s - int(u["free_used_s"]))
    free_left = min(free_user_left, pool_left)
    paid = int(u["paid_balance_s"])
    day_left = max(0, s.cap_s - int(u["day_used_s"]))
    out.update(free_left_s=free_left, free_user_left_s=free_user_left, paid_balance_s=paid, day_left_s=day_left,
               total_used_s=int(u.get("total_used_s", 0)))
    if day_left < s.min_start_s:
        out.update(can_run=False, code="daily_cap",
                   message=f"You have reached the daily limit of {s.cap_s // 60} minutes. You can continue tomorrow ({_pretty(out['day_resets_on'])}).")
    elif free_left + paid < s.min_start_s:
        if out["pool_exhausted"] and paid < s.min_start_s:
            msg = (f"This month's quota of free use on this website has been used up. Free minutes return on "
                   f"{_pretty(out['free_resets_on'])}. You can still continue now at ₹{_price(s.price)} per minute.")
            out.update(can_run=False, code="pool_exhausted", message=msg)
        else:
            out.update(can_run=False, code="need_payment",
                       message=f"Your {s.free_s // 60} free minutes for this month are used up. Continue for ₹{_price(s.price)} per minute?")
    else:
        out.update(can_run=True, code="ok", message="")
    return out


def _pretty(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def _price(p: float) -> str:
    return str(int(p)) if float(p).is_integer() else f"{p:.2f}"


# ---------------------------------------------------------------- storage
class FirestoreStore:
    """Thin wrapper so the accounting above can be tested with an in-memory store."""

    def __init__(self):
        from firebase_admin import firestore
        self._fs = firestore
        self.db = firestore.client()

    def tx(self, paths, fn):
        refs = [self.db.document(p) for p in paths]

        @self._fs.transactional
        def run(t):
            docs = []
            for r in refs:
                snap = r.get(transaction=t)
                docs.append(snap.to_dict() if snap.exists else None)
            result, new = fn(docs)
            for r, d in zip(refs, new):
                if d is not None:
                    t.set(r, d)
            return result
        return run(self.db.transaction())

    def add(self, collection, data):
        _, ref = self.db.collection(collection).add(data)
        return ref.id

    def query(self, collection, field, value, limit=200):
        from google.cloud.firestore_v1.base_query import FieldFilter
        q = self.db.collection(collection).where(filter=FieldFilter(field, "==", value)).limit(limit)
        return [(d.id, d.to_dict()) for d in q.stream()]


def _paths(uid: str, now: float):
    return [f"billing_users/{uid}", f"billing_pool/{_keys(now)[0]}"]


# ---------------------------------------------------------------- operations
def status(store, uid: str | None, email: str | None, now: float | None = None) -> dict:
    now, s = now or time.time(), Settings()
    if not uid:
        pool = store.tx([f"billing_pool/{_keys(now)[0]}"], lambda d: (d[0], [None]))
        return {"signed_in": False, **summary(None, pool, now, s)}

    def fn(docs):
        return summary(_fresh_user(docs[0], email, now), docs[1], now, s), [None, None]
    out = store.tx(_paths(uid, now), fn)
    pending = [r for _, r in store.query("billing_requests", "uid", uid) if r.get("status") == "pending"]
    out.update(signed_in=True, email=email, is_admin=is_admin(email or ""),
               pending=[{"minutes": r["minutes"], "amount_inr": r["amount_inr"], "upi_ref": r["upi_ref"], "created": r["created"]}
                        for r in sorted(pending, key=lambda r: r["created"])])
    return out


def begin_run(store, uid: str, email: str, now: float | None = None) -> dict:
    """Reserve a run slot, or raise Denied explaining why the user cannot start."""
    now, s = now or time.time(), Settings()

    def fn(docs):
        u = _fresh_user(docs[0], email, now)
        st = summary(u, docs[1], now, s)
        if u["active_until"] > now:
            raise Denied("busy", "You already have an analysis running. Wait for it to finish, then try again.", 409, st)
        if not st["can_run"]:
            raise Denied(st["code"], st["message"], 429 if st["code"] == "daily_cap" else 402, st)
        u["active_until"] = now + LOCK_SECONDS
        return st, [u, None]
    return store.tx(_paths(uid, now), fn)


def end_run(store, uid: str, seconds: float, now: float | None = None) -> dict:
    """Charge a finished run: free minutes first, then paid balance; release the run slot."""
    now, s = now or time.time(), Settings()
    secs = max(1, math.ceil(seconds))

    def fn(docs):
        u = _fresh_user(docs[0], None, now)
        pool = dict(docs[1] or {"free_used_s": 0})
        st = summary(u, pool, now, s)
        use_free = min(st["free_left_s"], secs)
        u["free_used_s"] += use_free
        pool["free_used_s"] = int(pool.get("free_used_s", 0)) + use_free
        # A run that overshoots the remaining balance is not billed beyond zero.
        u["paid_balance_s"] = max(0, int(u["paid_balance_s"]) - (secs - use_free))
        u["day_used_s"] += secs
        u["total_used_s"] = int(u.get("total_used_s", 0)) + secs
        u["active_until"] = 0
        return summary(u, pool, now, s), [u, pool if use_free else None]
    return store.tx(_paths(uid, now), fn)


def request_payment(store, uid: str, email: str, minutes, upi_ref, now: float | None = None) -> dict:
    now, s = now or time.time(), Settings()
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise Denied("bad_request", "Enter the number of minutes as a whole number.", 400)
    if not 1 <= minutes <= s.max_buy_min:
        raise Denied("bad_request", f"You can buy between 1 and {s.max_buy_min} minutes at a time.", 400)
    ref = re.sub(r"\s+", "", str(upi_ref or ""))
    if not REF_RE.match(ref):
        raise Denied("bad_request", "Enter the UPI transaction ID / UTR exactly as your payment app shows it (letters and digits only).", 400)
    if store.query("billing_requests", "upi_ref", ref, limit=1):
        raise Denied("duplicate_ref", "This transaction ID has already been submitted.", 400)
    pending = [r for _, r in store.query("billing_requests", "uid", uid) if r.get("status") == "pending"]
    if len(pending) >= MAX_PENDING_PER_USER:
        raise Denied("too_many", "You already have payments waiting for confirmation. Please wait until they are approved.", 400)
    amount = math.ceil(minutes * s.price)
    rid = store.add("billing_requests", {"uid": uid, "email": email, "minutes": minutes, "amount_inr": amount,
                                         "upi_ref": ref, "status": "pending", "created": now})
    return {"ok": True, "id": rid, "minutes": minutes, "amount_inr": amount}


def admin_list(store, now: float | None = None) -> dict:
    now, s = now or time.time(), Settings()
    month = _keys(now)[0]
    pool = store.tx([f"billing_pool/{month}"], lambda d: (d[0] or {}, [None]))
    pending = sorted(({"id": i, **r} for i, r in store.query("billing_requests", "status", "pending")), key=lambda r: r["created"])
    return {"month": month, "pool_minutes": s.pool_s // 60, "pool_used_s": int(pool.get("free_used_s", 0)),
            "free_resets_on": next_month_start(now), "pending": pending}


def decide(store, req_id: str, approve: bool, admin_email: str, minutes=None, now: float | None = None) -> dict:
    now = now or time.time()
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", req_id or ""):
        raise Denied("bad_request", "Unknown request.", 404)
    req = store.tx([f"billing_requests/{req_id}"], lambda d: (d[0], [None]))
    if not req:
        raise Denied("bad_request", "Unknown request.", 404)
    credit = int(minutes) if minutes not in (None, "") else int(req["minutes"])
    if approve and not 0 < credit <= 10000:
        raise Denied("bad_request", "Minutes to credit must be a positive number.", 400)

    def fn(docs):
        r, u = docs
        if r.get("status") != "pending":
            raise Denied("already_decided", f"This request was already {r.get('status')}.", 409)
        r = {**r, "status": "approved" if approve else "rejected", "decided_by": admin_email, "decided_at": now}
        if not approve:
            return {"ok": True, "status": r["status"]}, [r, None]
        r["credited_minutes"] = credit
        u = _fresh_user(u, None, now)
        u["paid_balance_s"] = int(u["paid_balance_s"]) + credit * 60
        return {"ok": True, "status": "approved", "credited_minutes": credit}, [r, u]
    return store.tx([f"billing_requests/{req_id}", f"billing_users/{req['uid']}"], fn)
