"""Affective computing on EEG: interpretable affect indices + cross-validated decoding of the task/condition with selectable models."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

BANDS = {"delta": (1, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45)}


def _bands(sfreq):
    return {k: v for k, v in BANDS.items() if v[1] < sfreq / 2 - 1}


def band_power(epochs: np.ndarray, sfreq: float) -> np.ndarray:
    """epochs: n × C × T (volts) → log10 band power, n × (C·B)."""
    f, p = welch(epochs * 1e6, fs=sfreq, nperseg=min(epochs.shape[-1], int(sfreq * 1.0)), axis=-1)
    feats = []
    for lo, hi in _bands(sfreq).values():
        m = (f >= lo) & (f < hi)
        feats.append(np.log10(p[..., m].mean(-1) + 1e-12))
    return np.concatenate(feats, axis=1)


def differential_entropy(epochs: np.ndarray, sfreq: float) -> np.ndarray:
    """Differential entropy of band-filtered signals (Gaussian assumption: ½·ln(2πe·σ²)) as used in SEED-style emotion recognition."""
    feats = []
    for lo, hi in _bands(sfreq).values():
        sos = butter(4, [lo, min(hi, sfreq / 2 - 1)], btype="band", fs=sfreq, output="sos")
        y = sosfiltfilt(sos, epochs * 1e6, axis=-1)
        feats.append(0.5 * np.log(2 * np.pi * np.e * y.var(-1) + 1e-12))
    return np.concatenate(feats, axis=1)


def _idx(ch_names, name):
    low = [c.lower() for c in ch_names]
    return low.index(name.lower()) if name.lower() in low else None


def affect_indices(epochs: np.ndarray, ch_names: list[str], sfreq: float) -> dict:
    """Classic, interpretable EEG affect markers (mean ± SD across epochs).
    FAA = ln(alpha power right) − ln(alpha power left) at frontal pairs; higher = relatively greater left-frontal activity,
    traditionally linked to approach motivation / positive affect (contested, small effects).
    Arousal index = beta / alpha power ratio (higher ≈ more cortical activation)."""
    f, p = welch(epochs * 1e6, fs=sfreq, nperseg=min(epochs.shape[-1], int(sfreq * 1.0)), axis=-1)
    a = (f >= 8) & (f < 13); b = (f >= 13) & (f < 30)
    alpha = p[..., a].mean(-1); beta = p[..., b].mean(-1)       # n × C
    out = {}
    for r, l in (("F4", "F3"), ("F8", "F7"), ("Fp2", "Fp1")):
        i, j = _idx(ch_names, r), _idx(ch_names, l)
        if i is not None and j is not None:
            v = np.log(alpha[:, i] + 1e-12) - np.log(alpha[:, j] + 1e-12)
            out[f"FAA_{r}-{l}"] = {"mean": round(float(v.mean()), 4), "sd": round(float(v.std()), 4)}
    ar = np.log(beta.mean(1) + 1e-12) - np.log(alpha.mean(1) + 1e-12)
    out["arousal_log_beta/alpha_all"] = {"mean": round(float(ar.mean()), 4), "sd": round(float(ar.std()), 4)}
    fr = [i for i in (_idx(ch_names, c) for c in ("Fp1", "Fp2", "F3", "F4", "F7", "F8", "Fz")) if i is not None]
    if fr:
        arf = np.log(beta[:, fr].mean(1) + 1e-12) - np.log(alpha[:, fr].mean(1) + 1e-12)
        out["arousal_log_beta/alpha_frontal"] = {"mean": round(float(arf.mean()), 4), "sd": round(float(arf.std()), 4)}
    return out


def evaluate_models(task_epochs: dict, ch_names: list[str], sfreq: float, model_ids: list[str], registry, seed: int = 0) -> dict:
    """Decode which task each epoch came from, with block-wise cross-validation (contiguous blocks never straddle train/test)."""
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    names = list(task_epochs)
    if len(names) < 2:
        return {"skipped": "decoding needs at least two tasks/conditions"}
    n_min = min(len(v) for v in task_epochs.values())
    if n_min < 20:
        return {"skipped": f"need ≥ 20 clean epochs per task for decoding (smallest task has {n_min})"}
    X, y, groups = [], [], []
    block = 10
    for ti, n in enumerate(names):
        ep = task_epochs[n]
        X.append(np.stack(ep)); y += [ti] * len(ep); groups += [ti * 10000 + i // block for i in range(len(ep))]
    X = np.concatenate(X); y = np.array(y); groups = np.array(groups)
    feats_cache = {}

    def feats(kind):
        if kind not in feats_cache:
            feats_cache[kind] = {"de": differential_entropy, "bp": band_power}[kind](X, sfreq)
        return feats_cache[kind]

    n_splits = int(max(2, min(5, len(np.unique(groups)) // 2, np.bincount(y).min() // block)))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    chance = float(np.bincount(y).max() / len(y))
    results = []
    for mid in model_ids:
        spec = registry.get(mid)
        if spec is None:
            results.append({"id": mid, "error": "unknown model"}); continue
        if spec["runtime"] != "function":
            results.append({"id": mid, "name": spec["name"], "error": "this model runs locally only (python -m eeg_tools.cli) — it is not enabled on the web service"}); continue
        ok, why = registry.is_available(spec)
        if not ok:
            results.append({"id": mid, "name": spec["name"], "error": why}); continue
        Xin = X if spec["input"] == "epochs" else feats(spec["input"])
        preds = np.zeros_like(y); good = True
        try:
            for tr, te in cv.split(Xin, y, groups):
                est = spec["build"](seed)
                est.fit(Xin[tr], y[tr])
                preds[te] = est.predict(Xin[te])
        except Exception as e:  # keep one failing model from sinking the whole request
            good = False
            results.append({"id": mid, "name": spec["name"], "error": f"{type(e).__name__}: {str(e)[:160]}"})
        if good:
            results.append({"id": mid, "name": spec["name"], "family": spec["family"], "accuracy": round(float((preds == y).mean()), 4),
                            "balanced_accuracy": round(float(balanced_accuracy_score(y, preds)), 4),
                            "macro_f1": round(float(f1_score(y, preds, average="macro")), 4),
                            "confusion": confusion_matrix(y, preds, labels=range(len(names))).tolist(), "n_splits": n_splits})
    results.sort(key=lambda r: -r.get("balanced_accuracy", -1))
    return {"classes": names, "n_epochs": int(len(y)), "chance_level": round(chance, 4), "cv": f"{n_splits}-fold stratified, contiguous {block}-epoch blocks held out together",
            "models": results, "feature_note": "DE = differential entropy per band & channel; BP = log band power; Riemannian models use epoch covariance matrices."}
