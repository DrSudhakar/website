"""Billing rules: free minutes, shared monthly pool, paid balance, daily cap, payment approval."""
import copy, itertools, os, sys
from datetime import datetime
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import billing


class MemoryStore:
    """Same interface as billing.FirestoreStore, kept in a dict (a failed transaction changes nothing)."""
    def __init__(self):
        self.docs, self._ids = {}, itertools.count(1)

    def tx(self, paths, fn):
        result, new = fn([copy.deepcopy(self.docs.get(p)) for p in paths])
        for p, d in zip(paths, new):
            if d is not None:
                self.docs[p] = copy.deepcopy(d)
        return result

    def add(self, collection, data):
        i = f"r{next(self._ids)}"
        self.docs[f"{collection}/{i}"] = copy.deepcopy(data)
        return i

    def query(self, collection, field, value, limit=200):
        out = [(p.split("/", 1)[1], copy.deepcopy(d)) for p, d in self.docs.items() if p.startswith(collection + "/") and d.get(field) == value]
        return out[:limit]


ENV = {"FREE_MINUTES_PER_USER": "5", "FREE_POOL_MINUTES": "10", "PRICE_PER_MINUTE_INR": "1", "DAILY_CAP_MINUTES": "120",
       "ADMIN_EMAILS": "owner@example.com"}
T0 = datetime(2026, 11, 13, 10, 0, tzinfo=billing.IST).timestamp()


@pytest.fixture(autouse=True)
def env():
    with mock.patch.dict(os.environ, ENV):
        yield


def run(store, uid, secs, now):
    billing.begin_run(store, uid, f"{uid}@x.com", now)
    return billing.end_run(store, uid, secs, now + secs)


def test_free_minutes_then_payment_needed():
    st = MemoryStore()
    s = run(st, "a", 200, T0)
    assert s["free_left_s"] == 100 and s["can_run"]
    s = run(st, "a", 90, T0 + 1000)                      # 10 s left < 30 s minimum to start
    assert s["free_left_s"] == 10 and not s["can_run"] and s["code"] == "need_payment" and "₹1 per minute" in s["message"]
    with pytest.raises(billing.Denied) as e:
        billing.begin_run(st, "a", "a@x.com", T0 + 2000)
    assert e.value.code == "need_payment" and e.value.http == 402


def test_pool_exhausted_blocks_free_use_for_everyone_until_next_month():
    st = MemoryStore()
    run(st, "a", 300, T0); run(st, "b", 300, T0 + 10)      # pool of 10 min now used up
    with pytest.raises(billing.Denied) as e:
        billing.begin_run(st, "c", "c@x.com", T0 + 20)      # c never used anything, but the pool is empty
    assert e.value.code == "pool_exhausted" and "1 December 2026" in e.value.message
    nxt = datetime(2026, 12, 1, 0, 5, tzinfo=billing.IST).timestamp()
    assert billing.begin_run(st, "c", "c@x.com", nxt)["free_left_s"] == 300


def test_paid_minutes_work_after_pool_is_empty_and_are_charged():
    st = MemoryStore()
    run(st, "a", 300, T0); run(st, "b", 300, T0 + 10)
    r = billing.request_payment(st, "c", "c@x.com", 20, "4312 3456 7890", T0 + 20)
    assert r["amount_inr"] == 20
    assert billing.status(st, "c", "c@x.com", T0 + 21)["pending"][0]["upi_ref"] == "431234567890"
    billing.decide(st, r["id"], True, "owner@example.com", None, T0 + 30)
    s = run(st, "c", 125, T0 + 40)
    assert s["paid_balance_s"] == 20 * 60 - 125 and s["free_left_s"] == 0
    with pytest.raises(billing.Denied) as e:                # cannot approve twice
        billing.decide(st, r["id"], True, "owner@example.com", None, T0 + 50)
    assert e.value.code == "already_decided"


def test_free_minutes_are_used_before_paid_and_overshoot_is_not_billed_below_zero():
    st = MemoryStore()
    r = billing.request_payment(st, "a", "a@x.com", 1, "ABC123456", T0)
    billing.decide(st, r["id"], True, "owner@example.com", None, T0)
    s = run(st, "a", 400, T0 + 5)                        # 300 free + 60 paid available, run takes 400 s
    assert s["free_left_s"] == 0 and s["paid_balance_s"] == 0


def test_daily_cap_and_single_run_at_a_time():
    st = MemoryStore()
    r = billing.request_payment(st, "a", "a@x.com", 300, "CAP0000001", T0)
    billing.decide(st, r["id"], True, "owner@example.com", None, T0)
    billing.begin_run(st, "a", "a@x.com", T0)
    with pytest.raises(billing.Denied) as e:
        billing.begin_run(st, "a", "a@x.com", T0 + 1)
    assert e.value.code == "busy" and e.value.http == 409
    billing.end_run(st, "a", 120 * 60 - 10, T0 + 7190)
    with pytest.raises(billing.Denied) as e:
        billing.begin_run(st, "a", "a@x.com", T0 + 7200)
    assert e.value.code == "daily_cap" and "14 November 2026" in e.value.message
    assert billing.begin_run(st, "a", "a@x.com", T0 + 86400)["can_run"]


def test_payment_request_validation():
    st = MemoryStore()
    for minutes, ref in [(0, "ABC123456"), (601, "ABC123456"), ("x", "ABC123456"), (10, "12"), (10, "<script>")]:
        with pytest.raises(billing.Denied):
            billing.request_payment(st, "a", "a@x.com", minutes, ref, T0)
    billing.request_payment(st, "a", "a@x.com", 10, "SAME123456", T0)
    with pytest.raises(billing.Denied) as e:
        billing.request_payment(st, "b", "b@x.com", 10, "SAME123456", T0)
    assert e.value.code == "duplicate_ref"


def test_admin_can_change_minutes_and_reject():
    st = MemoryStore()
    a = billing.request_payment(st, "a", "a@x.com", 30, "PAID000001", T0)
    b = billing.request_payment(st, "a", "a@x.com", 30, "PAID000002", T0)
    assert len(billing.admin_list(st, T0)["pending"]) == 2
    assert billing.decide(st, a["id"], True, "owner@example.com", 25, T0)["credited_minutes"] == 25
    billing.decide(st, b["id"], False, "owner@example.com", None, T0)
    assert billing.status(st, "a", "a@x.com", T0)["paid_balance_s"] == 25 * 60
    assert billing.admin_list(st, T0)["pending"] == []
    assert billing.is_admin("Owner@Example.com") and not billing.is_admin("a@x.com") and not billing.is_admin("")
