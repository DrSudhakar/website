"""Synthetic multichannel EEG with known microstate structure — for tests and the website's 'try demo data' button."""
from __future__ import annotations

import mne
import numpy as np

CHS_1020 = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "T7", "C3", "Cz", "C4", "T8", "P7", "P3", "Pz", "P4", "P8", "O1", "O2"]


def _templates(ch_names, k, seed):
    """k smooth, distinct scalp maps built from low-order spatial functions of electrode position."""
    info = mne.create_info(ch_names, 250.0, "eeg")
    info.set_montage(mne.channels.make_standard_montage("standard_1005"), match_case=False, on_missing="ignore")
    pos = np.array([info["chs"][i]["loc"][:3] for i in range(len(ch_names))])
    pos = pos / (np.linalg.norm(pos, axis=1, keepdims=True) + 1e-12)
    rng = np.random.default_rng(seed)
    maps = []
    for _ in range(k):
        w = rng.normal(size=(4, 3)) * 2.0
        m = sum(np.sin(w[j] @ pos.T + rng.uniform(0, 6.28)) for j in range(4))
        m -= m.mean()
        maps.append(m / np.linalg.norm(m))
    return np.array(maps)


def make_task(ch_names=CHS_1020, sfreq=250.0, seconds=60, state_probs=(0.4, 0.3, 0.2, 0.1), mean_dur=0.09, seed=0, noise=0.35,
              alpha_amp=0.3, template_seed=123, beta_amp=0.0, right_frontal_alpha=1.0):
    """Return mne.io.RawArray (µV scale) where each microstate map is active in segments of ~mean_dur seconds."""
    rng = np.random.default_rng(seed)
    k = len(state_probs)
    T = _templates(ch_names, k, template_seed)
    n = int(seconds * sfreq)
    seq = np.zeros(n, dtype=int)
    i = 0
    while i < n:
        d = max(int(sfreq * 0.03), int(rng.gamma(4.0, mean_dur * sfreq / 4.0)))
        seq[i:i + d] = rng.choice(k, p=np.asarray(state_probs) / np.sum(state_probs))
        i += d
    t = np.arange(n) / sfreq
    # amplitude modulated at ~ 10 Hz (so GFP has peaks inside each state) with random polarity flips
    amp = 1.0 + 0.6 * np.sin(2 * np.pi * 10 * t + rng.uniform(0, 6.28))
    pol = np.where(np.sin(2 * np.pi * 10 * t) >= 0, 1.0, -1.0)
    data = (T[seq].T * (amp * pol)) * 20.0  # µV
    data += alpha_amp * 10 * np.outer(rng.normal(size=len(ch_names)), np.sin(2 * np.pi * 10.5 * t + rng.uniform(0, 6.28)))
    if beta_amp:
        frontal = np.array([c in ("Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8") for c in ch_names], float)
        data += beta_amp * 10 * np.outer(0.4 + frontal, np.sin(2 * np.pi * 21 * t + rng.uniform(0, 6.28)))
    if right_frontal_alpha != 1.0:
        rf = np.array([c in ("Fp2", "F4", "F8") for c in ch_names], float)
        data += (right_frontal_alpha - 1.0) * 10 * np.outer(rf, np.sin(2 * np.pi * 10 * t + 1.0))
    data += noise * 10 * rng.normal(size=data.shape)
    info = mne.create_info(list(ch_names), sfreq, "eeg")
    raw = mne.io.RawArray(data * 1e-6, info, verbose="ERROR")
    raw.set_montage(mne.channels.make_standard_montage("standard_1005"), match_case=False, on_missing="ignore", verbose="ERROR")
    return raw, seq


def demo_tasks(seconds=60, seed=0):
    """Two 'tasks' with different microstate dynamics; the second has frontal alpha asymmetry added (as an affect signal)."""
    a, _ = make_task(seconds=seconds, state_probs=(0.45, 0.30, 0.15, 0.10), seed=seed)
    b, _ = make_task(seconds=seconds, state_probs=(0.10, 0.15, 0.30, 0.45), mean_dur=0.11, seed=seed + 1, beta_amp=0.8, right_frontal_alpha=2.2)
    return {"Task A (demo: calm film)": a, "Task B (demo: tense film)": b}
