"""Read an uploaded EEG recording into an mne.io.Raw (EEG channels only)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import mne
import numpy as np

ALLOWED = {".edf", ".bdf", ".set", ".fif", ".csv", ".txt", ".npy"}
MAX_BYTES = 30 * 1024 * 1024


class EEGReadError(ValueError):
    pass


def _from_array(x: np.ndarray, names: list[str] | None, sfreq: float | None) -> mne.io.BaseRaw:
    if sfreq is None or sfreq <= 0:
        raise EEGReadError("sampling rate (Hz) is required for CSV / NPY files")
    if x.ndim != 2:
        raise EEGReadError("array must be 2-D (channels × samples or samples × channels)")
    if x.shape[0] > x.shape[1]:   # samples × channels → transpose
        x = x.T
    names = names if names and len(names) == x.shape[0] else [f"EEG{i + 1}" for i in range(x.shape[0])]
    # assume µV if values look like µV (std > 1e-3), otherwise volts
    scale = 1e-6 if np.nanstd(x) > 1e-3 else 1.0
    return mne.io.RawArray(np.nan_to_num(x) * scale, mne.create_info(names, float(sfreq), "eeg"), verbose="ERROR")


def read_eeg(filename: str, content: bytes, sfreq: float | None = None) -> mne.io.BaseRaw:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise EEGReadError(f"unsupported file type '{ext}'. Use one of: {', '.join(sorted(ALLOWED))}")
    if len(content) > MAX_BYTES:
        raise EEGReadError("file too large for the web service (30 MB). Use the command-line tool for big files.")
    if ext in (".csv", ".txt"):
        text = content.decode("utf-8", "replace").splitlines()
        header = None
        first = text[0].replace(";", ",").replace("\t", ",").split(",") if text else []
        try:
            [float(v) for v in first if v.strip()]
        except ValueError:
            header = [h.strip() for h in first if h.strip()]
        rows = [[float(v) for v in ln.replace(";", ",").replace("\t", ",").split(",") if v.strip()] for ln in text[1 if header else 0:] if ln.strip()]
        arr = np.array(rows, dtype=float)
        if header and arr.shape[1] == len(header) + 1:   # drop a time column
            arr, header = arr[:, 1:], header
        raw = _from_array(arr, header if header and arr.shape[1] == len(header) else None, sfreq)
        return raw
    if ext == ".npy":
        import io
        return _from_array(np.load(io.BytesIO(content), allow_pickle=False), None, sfreq)
    # file-based readers need a real path
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "upload" + ext)
        Path(p).write_bytes(content)
        try:
            if ext == ".edf":
                raw = mne.io.read_raw_edf(p, preload=True, verbose="ERROR")
            elif ext == ".bdf":
                raw = mne.io.read_raw_bdf(p, preload=True, verbose="ERROR")
            elif ext == ".set":
                raw = mne.io.read_raw_eeglab(p, preload=True, verbose="ERROR")
            else:
                raw = mne.io.read_raw_fif(p, preload=True, verbose="ERROR")
        except Exception as e:  # mne raises many types
            raise EEGReadError(f"could not read {ext} file: {str(e)[:200]}") from None
    raw.pick(picks="eeg", exclude=[]) if len(mne.pick_types(raw.info, eeg=True)) else None
    return raw
