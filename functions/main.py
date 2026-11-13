"""Firebase Cloud Functions (2nd gen, Python) for the website's heavy demos.

  GET  api_status    → which models/services are ready
  GET  account       → the signed-in user's minutes;  POST account → payment requests and admin actions (billing.py)
  POST empathy_run   → LLM empathy benchmark          (functions/empathy.py)       — sign-in + minutes required
  POST eeg_analyze   → EEG preprocessing + microstates + affect decoding (eeg_tools) — sign-in + minutes required

Security model (read this before deploying):
  * empathy_run and eeg_analyze need a Firebase sign-in token and remaining free or paid minutes (billing.py).
  * CORS only allows the origins listed in ALLOWED_ORIGINS (functions/.env).
  * API keys typed by visitors are used for that one request and are never stored or logged.
  * Your own Hugging Face token (secret HF_TOKEN) is only used for open-model calls; usage is capped by
    max_instances, per-IP rate limits and the per-request limits in empathy.LIMITS. Also set a Google Cloud budget alert.
"""
from __future__ import annotations

import collections
import json
import os
import time

from firebase_admin import initialize_app
from firebase_functions import https_fn, options
from firebase_functions.options import set_global_options

initialize_app()
REGION = os.environ.get("FUNCTION_REGION", "asia-south1")   # Mumbai: closest to India. Change in functions/.env if you like.
set_global_options(region=REGION)

ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]
CORS = options.CorsOptions(cors_origins=ORIGINS, cors_methods=["GET", "POST", "OPTIONS"])
DEFAULT_JUDGE = os.environ.get("DEFAULT_JUDGE_MODEL", "Qwen/Qwen2.5-72B-Instruct")

_hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)


def _rate_limited(req, bucket: str, per_hour: int) -> bool:
    """Best-effort per-instance limiter (each instance keeps its own counters)."""
    ip = (req.headers.get("X-Forwarded-For", req.remote_addr or "?")).split(",")[0].strip()
    q = _hits[f"{bucket}:{ip}"]
    now = time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= per_hour:
        return True
    q.append(now)
    return False


def _json(obj, status=200):
    def conv(o):
        try:
            import numpy as np
            if isinstance(o, np.generic):
                return o.item()
            if isinstance(o, np.ndarray):
                return o.tolist()
        except ImportError:
            pass
        raise TypeError(f"not serialisable: {type(o)}")
    return https_fn.Response(json.dumps(obj, default=conv), status=status, mimetype="application/json")


_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        import billing
        _STORE = billing.FirestoreStore()
    return _STORE


def _verify(token: str) -> tuple[str, str]:
    from firebase_admin import auth
    d = auth.verify_id_token(token)
    return d["uid"], (d.get("email") or "").lower() if d.get("email_verified") else ""


def _user(req):
    h = req.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    try:
        return _verify(h[7:].strip())
    except Exception:
        return None


def _metered(req, work):
    """Run `work()` only for a signed-in user with minutes left, then charge the time it took."""
    import billing
    user = _user(req)
    if not user:
        return _json({"error": "Please sign in to use this tool.", "code": "signin"}, 401)
    try:
        billing.begin_run(_store(), *user)
    except billing.Denied as d:
        return _json({"error": d.message, "code": d.code, "account": d.status}, d.http)
    t0 = time.time()
    try:
        return work()
    finally:
        try:
            billing.end_run(_store(), user[0], time.time() - t0)
        except Exception as e:   # never lose the user's result because of a billing hiccup
            print(f"billing.end_run failed for {user[0]}: {e!r}")


@https_fn.on_request(cors=CORS, memory=options.MemoryOption.MB_256, max_instances=3)
def account(req: https_fn.Request) -> https_fn.Response:
    import billing
    user = _user(req)
    if req.method == "GET":
        return _json(billing.status(_store(), *(user or (None, None))))
    if req.method != "POST":
        return _json({"error": "GET or POST required"}, 405)
    if not user:
        return _json({"error": "Please sign in first.", "code": "signin"}, 401)
    if _rate_limited(req, "account", 60):
        return _json({"error": "Too many requests. Please try again later."}, 429)
    body = req.get_json(silent=True) or {}
    action = body.get("action")
    try:
        if action == "request":
            return _json(billing.request_payment(_store(), *user, body.get("minutes"), body.get("upi_ref")))
        if action in ("admin_list", "approve", "reject"):
            if not billing.is_admin(user[1]):
                return _json({"error": "Only the site owner can do this."}, 403)
            if action == "admin_list":
                return _json(billing.admin_list(_store()))
            return _json(billing.decide(_store(), str(body.get("id", "")), action == "approve", user[1], body.get("minutes")))
    except billing.Denied as d:
        return _json({"error": d.message, "code": d.code}, d.http)
    return _json({"error": "unknown action"}, 400)


@https_fn.on_request(cors=CORS, memory=options.MemoryOption.MB_256, max_instances=2)
def api_status(req: https_fn.Request) -> https_fn.Response:
    from eeg_tools import registry
    return _json({"ok": True, "default_judge": DEFAULT_JUDGE,
                  "eeg_models": [{"id": m["id"], "runtime": m["runtime"], "available": registry.is_available(m)[0]} for m in registry.MODELS]})


@https_fn.on_request(cors=CORS, timeout_sec=300, memory=options.MemoryOption.MB_512, max_instances=3, secrets=["HF_TOKEN"])
def empathy_run(req: https_fn.Request) -> https_fn.Response:
    import empathy
    if req.method != "POST":
        return _json({"error": "POST required"}, 405)
    if _rate_limited(req, "empathy", 12):
        return _json({"error": "Rate limit reached (12 runs/hour). Please try again later."}, 429)
    body = req.get_json(silent=True) or {}
    judge = body.get("judge")
    if judge is None:                     # default judge: open model on HF using the site's token
        judge = {"provider": "hf", "model": DEFAULT_JUDGE}
    elif judge is False:
        judge = None
    if not body.get("models"):
        return _json({"error": "Select at least one model."}, 400)

    def work():
        try:
            res = empathy.run_benchmark(
                models=list(body.get("models", []))[:20], scenario_ids=body.get("scenarios"), n_scenarios=int(body.get("n_scenarios", 6)),
                judge_cfg=judge, server_keys={"hf": os.environ.get("HF_TOKEN", "")})
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        return _json(res)
    return _metered(req, work)


@https_fn.on_request(cors=CORS, timeout_sec=300, memory=options.MemoryOption.GB_4, cpu=2, max_instances=2)
def eeg_analyze(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return _json({"error": "POST required"}, 405)
    if _rate_limited(req, "eeg", 10):
        return _json({"error": "Rate limit reached (10 analyses/hour). Please try again later."}, 429)
    if (req.content_length or 0) > 31 * 1024 * 1024:
        return _json({"error": "Upload too large for the web service (31 MB total). Use the command-line tool for big files."}, 413)
    return _metered(req, lambda: _eeg_work(req))


def _eeg_work(req):
    from eeg_tools import run
    from eeg_tools.io import EEGReadError, MAX_BYTES
    try:
        opts = json.loads(req.form.get("options", "{}"))
        opts = {k: v for k, v in opts.items() if k in {"k", "microstates", "affect", "models", "ica", "notch", "l_freq", "h_freq", "per_task_maps"}}
        if str(req.form.get("demo", "")) == "1":
            return _json(run.run_demo(opts))
        names = json.loads(req.form.get("names", "[]"))
        sfreq = float(req.form["sfreq"]) if req.form.get("sfreq") else None
        files = []
        for i, f in enumerate(req.files.getlist("files")):
            data = f.read()
            if len(data) > MAX_BYTES:
                return _json({"error": f"{f.filename}: file too large"}, 413)
            files.append({"name": names[i] if i < len(names) else f.filename, "filename": f.filename or f"file{i}.edf", "content": data})
        if not files:
            return _json({"error": "no files uploaded"}, 400)
        return _json(run.run_analysis(run.read_files(files, sfreq), opts))
    except (EEGReadError, ValueError, json.JSONDecodeError) as e:
        return _json({"error": str(e)}, 400)
