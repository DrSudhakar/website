"""Exercises the HTTP entry points through Flask's test client (no Firebase emulator needed)."""
import io, json, os, sys
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ALLOWED_ORIGINS", "https://me.github.io")
import flask
import pytest
with mock.patch("firebase_admin.initialize_app"):
    import main
import empathy
from tests.test_billing import MemoryStore

TOKENS = {"tok-user": ("u1", "user@x.com"), "tok-owner": ("o1", "owner@example.com")}
AUTH = {"Authorization": "Bearer tok-user"}


def fake_verify(token):
    if token not in TOKENS:
        raise ValueError("bad token")
    return TOKENS[token]


@pytest.fixture(autouse=True)
def backend():
    store = MemoryStore()
    with mock.patch.object(main, "_verify", fake_verify), mock.patch.object(main, "_STORE", store), \
         mock.patch.dict(os.environ, {"ADMIN_EMAILS": "owner@example.com", "FREE_MINUTES_PER_USER": "5", "FREE_POOL_MINUTES": "900"}):
        main._hits.clear()
        yield store


def call(fn, **kw):
    app = flask.Flask("t")
    with app.test_request_context(**kw):
        r = fn(flask.request)
        return r.status_code, json.loads(r.get_data())


def test_status():
    code, body = call(main.api_status, method="GET")
    assert code == 200 and any(m["id"] == "logreg_de" and m["available"] for m in body["eeg_models"])


def test_heavy_endpoints_need_sign_in():
    code, body = call(main.empathy_run, method="POST", json={"models": [{"provider": "hf", "model": "m/x"}]})
    assert code == 401 and body["code"] == "signin"
    code, body = call(main.eeg_analyze, method="POST", data={"demo": "1"}, headers={"Authorization": "Bearer forged"})
    assert code == 401


def test_empathy_endpoint_validation_and_run(backend):
    code, body = call(main.empathy_run, method="GET")
    assert code == 405
    code, body = call(main.empathy_run, method="POST", json={"models": []}, headers=AUTH)
    assert code == 400
    from tests.test_empathy import fake_post
    with mock.patch.object(empathy, "_post", fake_post), mock.patch.dict(os.environ, {"HF_TOKEN": "x"}):
        code, body = call(main.empathy_run, method="POST", json={"models": [{"provider": "hf", "model": "warm/model"}], "n_scenarios": 2}, headers=AUTH)
    assert code == 200 and body["models"][0]["summary"]["overall"] > 50
    u = backend.docs["billing_users/u1"]
    assert u["free_used_s"] >= 1 and u["active_until"] == 0


def test_eeg_demo_endpoint_and_bad_upload():
    code, body = call(main.eeg_analyze, method="POST", data={"demo": "1", "options": json.dumps({"k": 4, "models": ["logreg_de"]})}, headers=AUTH)
    assert code == 200 and body["microstates"]["k"] == 4
    code, body = call(main.eeg_analyze, method="POST", data={"files": (io.BytesIO(b"not an eeg file"), "x.edf"), "names": '["A"]'},
                      content_type="multipart/form-data", headers=AUTH)
    assert code == 400 and "could not read" in body["error"]
    # CSV upload round trip (channels in columns, header with names)
    from eeg_tools.synthetic import make_task
    ra, _ = make_task(seconds=40, seed=1); rb, _ = make_task(seconds=40, state_probs=(.1, .1, .4, .4), seed=2)
    def csv(raw):
        x = raw.get_data(units="uV").T
        return (",".join(raw.ch_names) + "\n" + "\n".join(",".join(f"{v:.3f}" for v in row) for row in x)).encode()
    code, body = call(main.eeg_analyze, method="POST", content_type="multipart/form-data", headers=AUTH,
                      data={"files": [(io.BytesIO(csv(ra)), "a.csv"), (io.BytesIO(csv(rb)), "b.csv")], "names": '["Rest","Task"]', "sfreq": "250",
                            "options": json.dumps({"k": 4, "models": ["logreg_de"]})})
    assert code == 200, body
    assert set(body["microstates"]["summary"]) == {"Rest", "Task"}


def test_out_of_minutes_returns_402_with_account(backend):
    backend.docs["billing_users/u1"] = {"free_used_s": 300, "paid_balance_s": 0}
    with mock.patch("billing._keys", return_value=("same", "same")):
        backend.docs["billing_users/u1"].update(month="same", day="same", day_used_s=0)
        code, body = call(main.eeg_analyze, method="POST", data={"demo": "1"}, headers=AUTH)
    assert code == 402 and body["code"] == "need_payment" and body["account"]["can_run"] is False


def test_account_flow_request_and_admin_approval(backend):
    code, body = call(main.account, method="GET")
    assert code == 200 and body["signed_in"] is False and body["price_per_minute"] == 1
    code, body = call(main.account, method="GET", headers=AUTH)
    assert code == 200 and body["free_left_s"] == 300 and body["is_admin"] is False
    code, body = call(main.account, method="POST", json={"action": "request", "minutes": 15, "upi_ref": "431234567890"}, headers=AUTH)
    assert code == 200 and body["amount_inr"] == 15
    code, body = call(main.account, method="POST", json={"action": "admin_list"}, headers=AUTH)
    assert code == 403
    owner = {"Authorization": "Bearer tok-owner"}
    code, body = call(main.account, method="POST", json={"action": "admin_list"}, headers=owner)
    assert code == 200 and len(body["pending"]) == 1
    code, body = call(main.account, method="POST", json={"action": "approve", "id": body["pending"][0]["id"]}, headers=owner)
    assert code == 200 and body["credited_minutes"] == 15
    code, body = call(main.account, method="GET", headers=AUTH)
    assert body["paid_balance_s"] == 15 * 60 and body["pending"] == []
