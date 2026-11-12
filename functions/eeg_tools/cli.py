"""Command-line use (any file size, any model incl. deep ones):

    python -m eeg_tools.cli --task "Calm=calm.edf" --task "Tense=tense.edf" --k 4 --models logreg_de riemann_ts_lr eegnet --out result.json
    python -m eeg_tools.cli --demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import registry
from .io import read_eeg
from .run import run_analysis, run_demo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", action="append", default=[], help='"Name=path/to/file" (repeat for each task)')
    ap.add_argument("--sfreq", type=float, help="sampling rate for CSV/NPY files")
    ap.add_argument("--k", default="4", help="number of microstates, or 'auto'")
    ap.add_argument("--models", nargs="*", default=["logreg_de", "riemann_ts_lr"])
    ap.add_argument("--notch", type=float, default=50.0)
    ap.add_argument("--ica", action="store_true")
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--out", default="eeg_result.json")
    a = ap.parse_args(argv)
    if a.list_models:
        for m in registry.MODELS:
            ok, why = registry.is_available(m)
            print(f"{m['id']:18s} {m['runtime']:9s} {'ready' if ok else 'missing: ' + why:40s} {m['name']}")
        return 0
    opts = {"k": "auto" if a.k == "auto" else int(a.k), "models": a.models, "notch": a.notch, "ica": a.ica}
    if a.demo:
        res = run_demo(opts)
    else:
        raws = {}
        for t in a.task:
            name, _, path = t.partition("=")
            raws[name] = read_eeg(Path(path).name, Path(path).read_bytes() if Path(path).stat().st_size < 10**9 else b"", a.sfreq)
        res = run_analysis(raws, opts)
    if a.no_images and "microstates" in res:
        res["microstates"].pop("images", None)
    Path(a.out).write_text(json.dumps(res, indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
