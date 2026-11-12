"""Exercises the HTTP entry points through Flask's test client (no Firebase emulator needed)."""
import io, json, os, sys
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ALLOWED_ORIGINS", "https://me.github.io")
import flask
with mock.patch("firebase_admin.initialize_app"):
    import main
import empathy

def call(fn, **kw):
    app = flask.Flask("t")
    with app.test_request_context(**kw):
        r = fn(flask.request)
        return r.status_code, json.loads(r.get_data())

def test_status():
    code, body = call(main.api_status, method="GET")
    assert code == 200 and any(m["id"] == "logreg_de" and m["available"] for m in body["eeg_models"])

def test_empathy_endpoint_validation_and_run():
    code, body = call(main.empathy_run, method="GET")
    assert code == 405
    code, body = call(main.empathy_run, method="POST", json={"models": []})
    assert code == 400
    from tests.test_empathy import fake_post
    with mock.patch.object(empathy, "_post", fake_post), mock.patch.dict(os.environ, {"HF_TOKEN": "x"}):
        code, body = call(main.empathy_run, method="POST", json={"models": [{"provider": "hf", "model": "warm/model"}], "n_scenarios": 2})
    assert code == 200 and body["models"][0]["summary"]["overall"] > 50

def test_eeg_demo_endpoint_and_bad_upload():
    code, body = call(main.eeg_analyze, method="POST", data={"demo": "1", "options": json.dumps({"k": 4, "models": ["logreg_de"]})})
    assert code == 200 and body["microstates"]["k"] == 4
    code, body = call(main.eeg_analyze, method="POST", data={"files": (io.BytesIO(b"not an eeg file"), "x.edf"), "names": '["A"]'}, content_type="multipart/form-data")
    assert code == 400 and "could not read" in body["error"]
    # CSV upload round trip (channels in columns, header with names)
    import numpy as np
    from eeg_tools.synthetic import make_task
    ra, _ = make_task(seconds=40, seed=1); rb, _ = make_task(seconds=40, state_probs=(.1, .1, .4, .4), seed=2)
    def csv(raw):
        x = raw.get_data(units="uV").T
        return (",".join(raw.ch_names) + "\n" + "\n".join(",".join(f"{v:.3f}" for v in row) for row in x)).encode()
    code, body = call(main.eeg_analyze, method="POST", content_type="multipart/form-data",
                      data={"files": [(io.BytesIO(csv(ra)), "a.csv"), (io.BytesIO(csv(rb)), "b.csv")], "names": '["Rest","Task"]', "sfreq": "250",
                            "options": json.dumps({"k": 4, "models": ["logreg_de"]})})
    assert code == 200, body
    assert set(body["microstates"]["summary"]) == {"Rest", "Task"}
