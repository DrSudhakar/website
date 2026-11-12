"""EEG microstate analysis: modified K-means (Pascual-Marqui et al., 2012), back-fitting, per-task statistics and task comparison.

Pipeline
  1. GFP peaks from every good epoch of every task → pooled (equal weight per task) → group templates (polarity-invariant K-means)
  2. templates are back-fitted to each task's data → coverage, mean duration, occurrence, GEV, transition probabilities (per epoch)
  3. tasks are compared with non-parametric tests on the per-epoch metrics (+ effect size, FDR correction)
  4. (optional) microstates are also estimated independently per task and matched to the group maps (map stability)
"""
from __future__ import annotations

import base64
import io
import string
from itertools import combinations

import numpy as np
from scipy import stats
from scipy.optimize import linear_sum_assignment
from scipy.signal import find_peaks

LETTERS = list(string.ascii_uppercase)


# ----------------------------------------------------------------------------- core maths
def gfp(X: np.ndarray) -> np.ndarray:
    """Global field power: spatial standard deviation at each sample. X: channels × time (average referenced)."""
    return X.std(axis=0)


def _norm_rows(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)


def modified_kmeans(maps: np.ndarray, k: int, n_init: int = 10, max_iter: int = 200, tol: float = 1e-7, seed: int = 0):
    """Polarity-invariant clustering of topographies. maps: N × C. Returns (templates k×C unit-norm, gev, sigma2)."""
    rng = np.random.default_rng(seed)
    N, C = maps.shape
    if N < k:
        raise ValueError(f"only {N} GFP peaks available for {k} microstates — need more / longer clean data")
    g2 = (maps ** 2).sum(1) / C           # = gfp²
    best = None
    for _ in range(n_init):
        T = _norm_rows(maps[rng.choice(N, k, replace=False)])
        prev = -np.inf
        for _ in range(max_iter):
            corr = _norm_rows(maps) @ T.T                     # N × k  (cosine)
            lab = np.abs(corr).argmax(1)
            for j in range(k):
                Xj = maps[lab == j]
                if len(Xj) == 0:                              # re-seed an empty cluster with the worst-explained map
                    worst = np.argmin(np.abs(corr).max(1))
                    T[j] = _norm_rows(maps[worst:worst + 1])[0]
                    continue
                w, v = np.linalg.eigh(Xj.T @ Xj)
                T[j] = v[:, -1]
            resid = (g2 * (1 - np.abs(_norm_rows(maps) @ T.T).max(1) ** 2)).sum()
            crit = -resid
            if abs(crit - prev) < tol * max(1.0, abs(crit)):
                break
            prev = crit
        corr = np.abs(_norm_rows(maps) @ T.T).max(1)
        gev = float((g2 * corr ** 2).sum() / g2.sum())
        sigma2 = float((g2 * (1 - corr ** 2)).sum() * C / (N * (C - 1)))   # residual noise variance (Pascual-Marqui)
        if best is None or gev > best[1]:
            best = (T.copy(), gev, sigma2)
    return best


def cv_criterion(sigma2: float, C: int, k: int) -> float:
    """Cross-validation criterion for choosing K (smaller is better). Pascual-Marqui et al. 1995."""
    return sigma2 * ((C - 1) / (C - 1 - k)) ** 2


def backfit(X: np.ndarray, T: np.ndarray, min_samples: int = 3):
    """Assign every sample to its best-correlating template (|r|), then absorb runs shorter than min_samples.
    Returns (labels T, abs-correlation of each sample with its label)."""
    Xn = X.T / (np.linalg.norm(X.T, axis=1, keepdims=True) + 1e-12)
    corr = np.abs(Xn @ T.T)                         # T × k
    lab = corr.argmax(1)
    for _ in range(10):
        runs = _runs(lab)
        changed = False
        for s, e, l in runs:
            if e - s < min_samples:
                prev_l = lab[s - 1] if s > 0 else None
                next_l = lab[e] if e < len(lab) else None
                cands = [c for c in (prev_l, next_l) if c is not None and c != l]
                if cands:
                    best = max(cands, key=lambda c: corr[s:e, c].sum())
                    lab[s:e] = best
                    changed = True
        if not changed:
            break
    return lab, corr[np.arange(len(lab)), lab]


def _runs(lab: np.ndarray):
    if len(lab) == 0:
        return []
    idx = np.flatnonzero(np.diff(lab)) + 1
    starts = np.r_[0, idx]
    ends = np.r_[idx, len(lab)]
    return [(int(s), int(e), int(lab[s])) for s, e in zip(starts, ends)]


def epoch_metrics(lab: np.ndarray, gfp_t: np.ndarray, corr: np.ndarray, k: int, sfreq: float) -> dict:
    """Coverage (fraction of time), mean duration (ms), occurrence (per second), GEV and transition counts for one epoch."""
    runs = _runs(lab)
    sec = len(lab) / sfreq
    cov = np.array([(lab == j).mean() for j in range(k)])
    occ = np.zeros(k); dur = np.full(k, np.nan)
    for j in range(k):
        r = [e - s for s, e, l in runs if l == j]
        occ[j] = len(r) / sec
        if r:
            dur[j] = np.mean(r) / sfreq * 1000
    g2 = gfp_t ** 2
    gev = np.array([(g2[lab == j] * corr[lab == j] ** 2).sum() / max(g2.sum(), 1e-12) for j in range(k)])
    trans = np.zeros((k, k))
    for (_, _, a), (_, _, b) in zip(runs[:-1], runs[1:]):
        trans[a, b] += 1
    return {"coverage": cov, "duration": dur, "occurrence": occ, "gev": gev, "transitions": trans}


# ----------------------------------------------------------------------------- statistics helpers
def _fdr(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float); n = len(p)
    if n == 0:
        return p
    order = np.argsort(p); ranked = p[order] * n / (np.arange(n) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n); out[order] = np.minimum(ranked, 1.0)
    return out


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    gt = sum((x > b).sum() for x in a); lt = sum((x < b).sum() for x in a)
    return float((gt - lt) / (len(a) * len(b)))


# ----------------------------------------------------------------------------- plotting
def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90, bbox_inches="tight", transparent=False, facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def topomap_png(map_vec: np.ndarray, info, title: str = "") -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import mne
        # orient the map so the strongest absolute value is positive (polarity is arbitrary in microstates)
        v = map_vec * (1 if map_vec[np.abs(map_vec).argmax()] >= 0 else -1)
        fig, ax = plt.subplots(figsize=(1.7, 1.8))
        mne.viz.plot_topomap(v, info, axes=ax, show=False, contours=4, sensors=True, cmap="RdBu_r", vlim=(-np.abs(v).max(), np.abs(v).max()))
        ax.set_title(title, fontsize=11)
        return _fig_to_b64(fig)
    except Exception:
        return None


def segmentation_png(X: np.ndarray, lab: np.ndarray, sfreq: float, k: int, seconds: float = 2.0) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        n = int(seconds * sfreq)
        g = gfp(X[:, :n]); l = lab[:n]
        t = np.arange(len(g)) / sfreq
        cols = plt.get_cmap("tab10")
        fig, ax = plt.subplots(figsize=(6.5, 1.6))
        for s, e, c in _runs(l):
            ax.axvspan(t[s], t[min(e, len(t) - 1)], color=cols(c), alpha=0.35, lw=0)
        ax.plot(t, g * 1e6, color="black", lw=1)
        ax.set_xlabel("time (s)"); ax.set_ylabel("GFP (µV)")
        ax.set_xlim(0, seconds)
        handles = [plt.Rectangle((0, 0), 1, 1, color=cols(j), alpha=0.5) for j in range(k)]
        ax.legend(handles, LETTERS[:k], ncol=k, fontsize=7, loc="upper right", frameon=False)
        return _fig_to_b64(fig)
    except Exception:
        return None


# ----------------------------------------------------------------------------- main entry
def analyze(tasks: dict, info, k: int | str = 4, per_task_maps: bool = True, peaks_per_task: int = 2000, min_ms: float = 30.0,
            seed: int = 0, make_images: bool = True) -> dict:
    """tasks: {name: {"epochs": [C × T arrays (average-referenced, volts)], "sfreq": float}}  → JSON-serialisable dict."""
    names = list(tasks)
    sfreq = tasks[names[0]]["sfreq"]
    C = tasks[names[0]]["epochs"][0].shape[0]
    rng = np.random.default_rng(seed)
    # 1) GFP-peak maps per task
    task_peaks = {}
    for n in names:
        pk = []
        for ep in tasks[n]["epochs"]:
            g = gfp(ep)
            idx, _ = find_peaks(g, distance=max(1, int(0.01 * sfreq)))
            pk.append(ep[:, idx].T)
        task_peaks[n] = np.vstack(pk) if pk else np.empty((0, C))
        if len(task_peaks[n]) < 20:
            raise ValueError(f"task '{n}' has too little clean data for microstate analysis (only {len(task_peaks[n])} GFP peaks)")
    m = min(peaks_per_task, *(len(v) for v in task_peaks.values()))
    pooled = np.vstack([v[rng.choice(len(v), m, replace=False)] for v in task_peaks.values()])
    # 2) choose K
    k_search = None
    if k == "auto":
        k_search = []
        for kk in range(2, 8):
            T, gev, s2 = modified_kmeans(pooled, kk, n_init=4, seed=seed)
            k_search.append({"k": kk, "gev": round(gev, 4), "cv": cv_criterion(s2, C, kk)})
        k = min(k_search, key=lambda r: r["cv"])["k"]
        for r in k_search:
            r["cv"] = float(f"{r['cv']:.6g}")
    k = int(k)
    T, gev_group, _ = modified_kmeans(pooled, k, n_init=12, seed=seed)
    # order templates by group GEV (largest first) and name A, B, C…
    gp = pooled / (np.linalg.norm(pooled, axis=1, keepdims=True) + 1e-12)
    lab_g = np.abs(gp @ T.T).argmax(1)
    share = np.array([(lab_g == j).mean() for j in range(k)])
    order = np.argsort(-share)
    T = T[order]
    states = LETTERS[:k]
    min_samples = max(2, int(round(min_ms / 1000 * sfreq)))
    # 3) back-fit per task → per-epoch metrics
    per_epoch = {n: {"coverage": [], "duration": [], "occurrence": [], "gev": []} for n in names}
    trans_sum = {n: np.zeros((k, k)) for n in names}
    first_seg = {}
    for n in names:
        for i, ep in enumerate(tasks[n]["epochs"]):
            lab, cr = backfit(ep, T, min_samples)
            mt = epoch_metrics(lab, gfp(ep), cr, k, sfreq)
            for key in per_epoch[n]:
                per_epoch[n][key].append(mt[key])
            trans_sum[n] += mt["transitions"]
            if i == 0 and make_images:
                first_seg[n] = (ep, lab)
    summary = {}
    for n in names:
        summary[n] = {"n_epochs": len(per_epoch[n]["coverage"])}
        for key in ("coverage", "duration", "occurrence", "gev"):
            arr = np.array(per_epoch[n][key])            # epochs × k
            mean = np.nanmean(arr, 0); sd = np.nanstd(arr, 0)
            scale = 100.0 if key in ("coverage", "gev") else 1.0   # percent
            summary[n][key] = {"mean": (mean * scale).round(3).tolist(), "sd": (sd * scale).round(3).tolist(),
                               "sem": (sd / np.sqrt(max(1, arr.shape[0])) * scale).round(3).tolist()}
        tm = trans_sum[n]; rowsum = tm.sum(1, keepdims=True)
        summary[n]["transition_prob"] = np.divide(tm, rowsum, out=np.zeros_like(tm), where=rowsum > 0).round(4).tolist()
        summary[n]["transition_counts"] = tm.astype(int).tolist()
        summary[n]["gev_total"] = round(float(np.sum(np.nanmean(np.array(per_epoch[n]["gev"]), 0))) * 100, 2)
    # 4) task comparison
    comparisons, ps = [], []
    for key in ("coverage", "duration", "occurrence"):
        for j in range(k):
            groups = {n: np.array([e[j] for e in per_epoch[n][key]], float) for n in names}
            if len(names) >= 3:
                vals = [g[~np.isnan(g)] for g in groups.values()]
                if all(len(v) > 1 for v in vals) and np.ptp(np.concatenate(vals)) > 0:
                    H, p = stats.kruskal(*vals); n_all = sum(len(v) for v in vals)
                    comparisons.append({"metric": key, "state": states[j], "test": "Kruskal–Wallis (all tasks)", "tasks": names, "stat": round(float(H), 3), "p": float(p), "effect": round(float((H - len(vals) + 1) / (n_all - len(vals))), 3), "effect_name": "epsilon²"})
                    ps.append(p)
            for a, b in combinations(names, 2):
                x, y = groups[a][~np.isnan(groups[a])], groups[b][~np.isnan(groups[b])]
                if len(x) < 2 or len(y) < 2 or np.ptp(np.concatenate([x, y])) == 0:
                    continue
                U, p = stats.mannwhitneyu(x, y, alternative="two-sided")
                comparisons.append({"metric": key, "state": states[j], "test": "Mann–Whitney U", "tasks": [a, b], "stat": round(float(U), 1), "p": float(p),
                                    "effect": round(_cliffs_delta(x, y), 3), "effect_name": "Cliff's δ", "means": [round(float(np.mean(x)), 4), round(float(np.mean(y)), 4)]})
                ps.append(p)
    q = _fdr(np.array(ps)) if ps else []
    for c, qv in zip(comparisons, q):
        c["q_fdr"] = round(float(qv), 5); c["p"] = round(c["p"], 5)
    comparisons.sort(key=lambda c: c["q_fdr"])
    # 5) task-specific maps and stability
    stability = {}
    task_maps = {}
    if per_task_maps:
        for n in names:
            Tn, gev_n, _ = modified_kmeans(task_peaks[n][rng.choice(len(task_peaks[n]), min(m * 2, len(task_peaks[n])), replace=False)], k, n_init=6, seed=seed)
            R = np.abs(T @ Tn.T)
            r, c = linear_sum_assignment(-R)
            matched = Tn[c]
            task_maps[n] = matched
            stability[n] = {"gev": round(gev_n * 100, 2), "spatial_corr_to_group": {states[i]: round(float(R[i, j]), 3) for i, j in zip(r, c)}}
    out = {"k": k, "states": states, "gev_group": round(gev_group * 100, 2), "k_search": k_search, "sfreq": sfreq, "n_channels": C,
           "summary": summary, "comparisons": comparisons, "map_stability": stability,
           "peaks_used_per_task": int(m), "min_segment_ms": min_ms}
    if make_images:
        out["images"] = {"group_maps": [topomap_png(T[j], info, states[j]) for j in range(k)],
                         "task_maps": {n: [topomap_png(task_maps[n][j], info, states[j]) for j in range(k)] for n in task_maps},
                         "segmentation": {n: segmentation_png(ep, lab, sfreq, k) for n, (ep, lab) in first_seg.items()}}
    out["templates"] = T.round(5).tolist()
    return out
