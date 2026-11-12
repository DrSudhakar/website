"""End-to-end EEG analysis: read → preprocess → microstates (per task + comparison) → affect indices and model decoding."""
from __future__ import annotations

import time

import mne
import numpy as np

from . import affect, microstates, registry
from .io import EEGReadError, read_eeg
from .preprocess import PreprocOptions, preprocess
from .synthetic import demo_tasks

MAX_TASKS = 6


def _epochs_from(raw, rep) -> list[np.ndarray]:
    X = raw.get_data()
    L, mask = rep["epoch_samples"], rep["good_epoch_mask"]
    return [X[:, i * L:(i + 1) * L] for i in range(len(mask)) if mask[i]]


def _common_channels(raws: dict) -> list[str]:
    sets = [{c.lower() for c in r.ch_names} for r in raws.values()]
    common = set.intersection(*sets)
    first = next(iter(raws.values()))
    return [c for c in first.ch_names if c.lower() in common]


def run_analysis(raw_by_task: dict, options: dict | None = None) -> dict:
    """raw_by_task: {task name: mne Raw}.  options: see keys below."""
    t0 = time.time()
    o = {"k": 4, "microstates": True, "affect": True, "models": ["logreg_de", "riemann_ts_lr"], "ica": False, "notch": 50.0,
         "l_freq": 1.0, "h_freq": 40.0, "per_task_maps": True, "seed": 0}
    o.update(options or {})
    if not raw_by_task:
        raise ValueError("no EEG data provided")
    if len(raw_by_task) > MAX_TASKS:
        raise ValueError(f"at most {MAX_TASKS} tasks per analysis")
    pre = PreprocOptions(l_freq=float(o["l_freq"]), h_freq=float(o["h_freq"]), notch=(float(o["notch"]) if o["notch"] else None), ica=bool(o["ica"]))
    cleaned, reports = {}, {}
    for name, raw in raw_by_task.items():
        cleaned[name], reports[name] = preprocess(raw, pre)
    # harmonise channels and sampling rate across tasks
    common = _common_channels(cleaned)
    if len(common) < 4:
        raise ValueError(f"tasks share only {len(common)} channel names; microstates need at least 4 common channels (≥ 19 recommended)")
    sf = min(r.info["sfreq"] for r in cleaned.values())
    for name, r in cleaned.items():
        r.pick(common)
        if abs(r.info["sfreq"] - sf) > 1e-6:
            # re-run epoch bookkeeping after resampling
            r.resample(sf, verbose="ERROR")
            reports[name]["epoch_samples"] = int(pre.epoch_len * sf)
            n_ep = r.get_data().shape[1] // reports[name]["epoch_samples"]
            reports[name]["good_epoch_mask"] = np.ones(n_ep, bool)
        reports[name]["n_channels"] = len(common)
    tasks = {n: {"epochs": _epochs_from(cleaned[n], reports[n]), "sfreq": sf} for n in cleaned}
    info = next(iter(cleaned.values())).info
    out = {"preprocessing": {}, "channels": common, "sfreq": sf}
    for n, rep in reports.items():
        out["preprocessing"][n] = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in rep.items() if k not in ("good_epoch_mask",)}
        out["preprocessing"][n]["n_good_epochs"] = len(tasks[n]["epochs"])
    if o["microstates"]:
        try:
            out["microstates"] = microstates.analyze(tasks, info, k=o["k"], per_task_maps=bool(o["per_task_maps"]), seed=int(o["seed"]))
        except ValueError as e:
            out["microstates"] = {"error": str(e)}
    if o["affect"]:
        aff = {"indices": {}}
        for n in tasks:
            if tasks[n]["epochs"]:
                aff["indices"][n] = affect.affect_indices(np.stack(tasks[n]["epochs"]), common, sf)
        aff["decoding"] = affect.evaluate_models({n: tasks[n]["epochs"] for n in tasks}, common, sf, list(o["models"]), registry, seed=int(o["seed"]))
        out["affect"] = aff
    out["seconds"] = round(time.time() - t0, 1)
    return out


def run_demo(options: dict | None = None) -> dict:
    return run_analysis(demo_tasks(seconds=60), options)


def read_files(files: list[dict], sfreq: float | None = None) -> dict:
    """files: [{name, filename, content(bytes)}] → {task name: Raw}"""
    out = {}
    for f in files:
        nm = (f.get("name") or f["filename"]).strip()[:60] or f["filename"]
        if nm in out:
            nm = f"{nm} ({len(out) + 1})"
        out[nm] = read_eeg(f["filename"], f["content"], sfreq)
    return out
