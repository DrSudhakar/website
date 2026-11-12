#!/usr/bin/env python3
"""Check that every EEG model we advertise really RUNS, and write the verdict to data/eeg_models.json.

  1. Built-in registry models (functions/eeg_tools/registry.py): trained + cross-validated on a small synthetic EEG task
     where two conditions differ in spectral content. Status "ok" only if the model runs AND clearly beats chance.
  2. Hugging Face candidates (data/eeg_candidates.json, found by update_eeg_models.py): the checkpoint is downloaded (if small),
     loaded with braindecode, and a forward pass on random EEG-shaped input must give finite output.

Statuses: ok | failed | unavailable (library not installed here) | skipped (e.g. checkpoint too large)
Run:  python scripts/test_eeg_models.py [--no-candidates] [--max-mb 400]
"""
import argparse
import importlib
import json
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "functions"))

from _common import http_json, load, save  # noqa: E402


def synthetic_epochs():
    import numpy as np
    from eeg_tools.synthetic import demo_tasks
    from eeg_tools.preprocess import preprocess
    tasks = {}
    for name, raw in demo_tasks(seconds=40, seed=3).items():
        clean, rep = preprocess(raw)
        X = clean.get_data(); L = rep["epoch_samples"]
        tasks[name] = [X[:, i * L:(i + 1) * L] for i in range(X.shape[1] // L)]
    return tasks, clean.ch_names, clean.info["sfreq"]


def test_registry():
    from eeg_tools import affect, registry
    tasks, chs, sf = synthetic_epochs()
    out = []
    for spec in registry.MODELS:
        rec = {"id": spec["id"], "name": spec["name"], "family": spec["family"], "runtime": spec["runtime"], "source": spec["source"],
               "description": spec["description"], "kind": "builtin"}
        ok, why = registry.is_available(spec)
        if not ok:
            rec.update(status="unavailable", detail=why)
        else:
            t0 = time.time()
            try:
                if spec["runtime"] == "local":      # deep nets: keep the CI check light
                    import numpy as np
                    from eeg_tools.deep import BraindecodeClassifier
                    X = np.stack(tasks[list(tasks)[0]] + tasks[list(tasks)[1]]); y = np.array([0] * len(tasks[list(tasks)[0]]) + [1] * len(tasks[list(tasks)[1]]))
                    idx = np.random.default_rng(0).permutation(len(y)); tr, te = idx[: int(0.7 * len(y))], idx[int(0.7 * len(y)):]
                    clf = BraindecodeClassifier(spec["arch"], epochs=15).fit(X[tr], y[tr])
                    acc = float((clf.predict(X[te]) == y[te]).mean())
                else:
                    res = affect.evaluate_models(tasks, chs, sf, [spec["id"]], registry)
                    r = res["models"][0]
                    if "error" in r:
                        raise RuntimeError(r["error"])
                    acc = r["balanced_accuracy"]
                rec.update(status="ok" if acc >= 0.75 else "failed", accuracy_on_synthetic=round(acc, 3),
                           detail="" if acc >= 0.75 else f"runs, but only {acc:.2f} balanced accuracy on an easy synthetic task",
                           seconds=round(time.time() - t0, 1))
            except Exception as e:
                rec.update(status="failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
        print(f"  [{rec['status']:11s}] {rec['id']}  {rec.get('detail', '')}")
        out.append(rec)
    return out


def test_candidate(c, max_mb):
    rec = {"id": c["id"], "name": c["id"], "family": "pretrained (Hugging Face)", "runtime": "local", "source": "huggingface.co/" + c["id"],
           "description": "Pretrained EEG encoder from Hugging Face. Verified to load and run; it is a feature extractor that needs fine-tuning on labelled data. Run locally via the command line.", "kind": "candidate", "downloads": c.get("downloads")}
    info = http_json(f"https://huggingface.co/api/models/{c['id']}?blobs=true")
    if not info:
        rec.update(status="failed", detail="model page not reachable"); return rec
    weights = [s for s in info.get("siblings", []) if s["rfilename"].endswith(".safetensors") and "/" not in s["rfilename"]]
    size_mb = sum(s.get("size") or 0 for s in weights) / 1e6
    if size_mb > max_mb:
        rec.update(status="skipped", detail=f"checkpoint {size_mb:.0f} MB exceeds {max_mb} MB test limit"); return rec
    if not weights:
        rec.update(status="skipped", detail="no top-level safetensors checkpoint to load"); return rec
    try:
        import numpy as np
        import torch
        import braindecode.models as bm
    except ImportError as e:
        rec.update(status="unavailable", detail=f"needs {e.name}"); return rec
    tags = {t.lower().replace("-", "").replace("_", ""): t for t in info.get("tags", [])}
    classes = {n.lower(): n for n in dir(bm) if n[:1].isupper()}
    cls_name = next((classes[t] for t in tags if t in classes), None)
    if not cls_name:
        rec.update(status="skipped", detail="no matching braindecode model class in the repo tags (needs a custom adapter)"); return rec
    t0 = time.time()
    try:
        model = getattr(bm, cls_name).from_pretrained(c["id"])
        model.eval()
        cfg = json.loads(__import__("urllib.request", fromlist=["urlopen"]).urlopen(f"https://huggingface.co/{c['id']}/raw/main/config.json", timeout=30).read())
        sfreq = cfg.get("sfreq") or 256
        n_chans = cfg.get("n_chans") or 19
        n_times = cfg.get("n_times") or int(round((cfg.get("input_window_seconds") or 4) * sfreq))
        with torch.no_grad():
            y = model(torch.randn(2, n_chans, n_times))
        y = y[0] if isinstance(y, (tuple, list)) else y
        if not torch.isfinite(y).all():
            raise RuntimeError("non-finite output")
        rec.update(status="ok", detail=f"loaded as braindecode.{cls_name}; input {n_chans} ch × {n_times} samples, output {tuple(y.shape)}", seconds=round(time.time() - t0, 1),
                   input_spec={"n_chans": n_chans, "n_times": n_times, "sfreq": sfreq}, params_m=round(sum(p.numel() for p in model.parameters()) / 1e6, 1))
    except Exception as e:
        rec.update(status="failed", detail=f"{type(e).__name__}: {str(e)[:200]}")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-candidates", action="store_true")
    ap.add_argument("--max-mb", type=float, default=400)
    a = ap.parse_args()
    print("Built-in models:")
    models = test_registry()
    if not a.no_candidates:
        print("Hugging Face candidates:")
        for c in load("eeg_candidates.json", {"candidates": []})["candidates"]:
            r = test_candidate(c, a.max_mb)
            print(f"  [{r['status']:11s}] {r['id']}  {r.get('detail', '')}")
            models.append(r)
    save("eeg_models.json", {"tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "python": sys.version.split()[0], "models": models})
    bad = [m["id"] for m in models if m["status"] == "failed" and m["kind"] == "builtin"]
    if bad:
        print("BUILT-IN MODELS FAILED:", bad); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
