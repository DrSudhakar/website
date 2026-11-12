"""Automatic EEG preprocessing (no manual steps): bad-channel handling, filtering, resampling, re-referencing, optional ICA, epoch rejection."""
from __future__ import annotations

from dataclasses import dataclass, field

import mne
import numpy as np


@dataclass
class PreprocOptions:
    l_freq: float = 1.0
    h_freq: float = 40.0
    notch: float | None = 50.0          # 50 Hz in India/Europe, 60 Hz in the Americas; None to skip
    resample: float | None = 250.0
    reference: str = "average"
    ica: bool = False                   # optional; removes eye-blink-like components using frontal channels as proxy EOG
    reject_ptp_uv: float = 150.0        # epochs with peak-to-peak above this are dropped
    epoch_len: float = 2.0              # seconds, for rejection and feature extraction
    max_seconds: float = 300.0          # use at most this much data per task (keeps the web service fast)


def _bad_channels(raw: mne.io.BaseRaw) -> list[str]:
    x = raw.get_data(units="uV")
    var = x.var(axis=1)
    med = np.median(var) + 1e-12
    flat = var < 1e-3 * med
    noisy = var > 20 * med
    return [raw.ch_names[i] for i in np.where(flat | noisy)[0]]


def preprocess(raw: mne.io.BaseRaw, opts: PreprocOptions | None = None) -> tuple[mne.io.BaseRaw, dict]:
    """Returns (clean continuous raw, report dict). Does not modify the input."""
    o = opts or PreprocOptions()
    raw = raw.copy().load_data()
    rep: dict = {"input_channels": len(raw.ch_names), "input_seconds": round(raw.times[-1], 1), "steps": []}
    if raw.times[-1] > o.max_seconds:
        raw.crop(0, o.max_seconds)
        rep["steps"].append(f"cropped to first {o.max_seconds:.0f} s")
    raw.pick(picks="eeg", exclude=[])
    # montage (for topographies / interpolation) — silently ignored for unknown channel names
    if raw.get_montage() is None:
        raw.set_montage(mne.channels.make_standard_montage("standard_1005"), match_case=False, on_missing="ignore", verbose="ERROR")
    has_pos = sum(np.any(np.isfinite(ch["loc"][:3]) & (ch["loc"][:3] != 0)) for ch in raw.info["chs"]) >= len(raw.ch_names) * 0.8
    bads = _bad_channels(raw)
    if len(bads) > len(raw.ch_names) // 4:
        bads = bads[: len(raw.ch_names) // 4]
    raw.info["bads"] = bads
    if bads:
        if has_pos:
            raw.interpolate_bads(reset_bads=True, verbose="ERROR")
            rep["steps"].append(f"interpolated bad channels: {', '.join(bads)}")
        else:
            raw.drop_channels(bads)
            rep["steps"].append(f"dropped bad channels (no positions to interpolate): {', '.join(bads)}")
    rep["bad_channels"] = bads
    nyq = raw.info["sfreq"] / 2
    if o.notch and o.notch < nyq - 1:
        raw.notch_filter([o.notch], verbose="ERROR")
        rep["steps"].append(f"notch {o.notch:g} Hz")
    h = min(o.h_freq, nyq - 1)
    raw.filter(o.l_freq, h, verbose="ERROR")
    rep["steps"].append(f"band-pass {o.l_freq:g}–{h:g} Hz")
    if o.resample and raw.info["sfreq"] > o.resample + 1e-6:
        raw.resample(o.resample, verbose="ERROR")
        rep["steps"].append(f"resampled to {o.resample:g} Hz")
    if o.ica and len(raw.ch_names) >= 8:
        try:
            ica = mne.preprocessing.ICA(n_components=min(15, len(raw.ch_names) - 1), method="fastica", random_state=0, max_iter=300)
            ica.fit(raw, verbose="ERROR")
            frontal = [c for c in raw.ch_names if c.lower() in ("fp1", "fp2", "af7", "af8", "fpz")]
            if frontal:
                idx, _ = ica.find_bads_eog(raw, ch_name=frontal[0], threshold=3.0, verbose="ERROR")
                ica.exclude = idx[:2]
                ica.apply(raw, verbose="ERROR")
                rep["steps"].append(f"ICA: removed {len(ica.exclude)} eye-related component(s)")
            else:
                rep["steps"].append("ICA skipped (no frontal channel to use as EOG proxy)")
        except Exception as e:  # ICA is best-effort
            rep["steps"].append(f"ICA failed and was skipped: {str(e)[:80]}")
    raw.set_eeg_reference("average", projection=False, verbose="ERROR")
    rep["steps"].append("average reference")
    # epoch-level artifact rejection → mask of good samples
    sf = raw.info["sfreq"]
    L = int(o.epoch_len * sf)
    X = raw.get_data(units="uV")
    n_ep = X.shape[1] // L
    good = np.ones(n_ep, dtype=bool)
    for e in range(n_ep):
        seg = X[:, e * L:(e + 1) * L]
        if np.ptp(seg, axis=1).max() > o.reject_ptp_uv:
            good[e] = False
    rep["epochs_total"], rep["epochs_kept"] = int(n_ep), int(good.sum())
    rep["steps"].append(f"rejected {int((~good).sum())} of {n_ep} epochs (peak-to-peak > {o.reject_ptp_uv:g} µV)")
    rep["sfreq"], rep["n_channels"], rep["seconds"] = sf, len(raw.ch_names), round(raw.times[-1], 1)
    rep["good_epoch_mask"] = good
    rep["epoch_samples"] = L
    return raw, rep
