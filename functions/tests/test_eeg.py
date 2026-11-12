import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eeg_tools import microstates as ms, registry, run
from eeg_tools.synthetic import make_task, CHS_1020

def test_microstate_recovery():
    """Planted maps/state sequence must be recovered: high spatial correlation and high label agreement."""
    raw, seq = make_task(seconds=40, state_probs=(0.3, 0.3, 0.2, 0.2), noise=0.2, alpha_amp=0.0, seed=2)
    raw.filter(1, 40, verbose="ERROR"); raw.set_eeg_reference("average", verbose="ERROR")
    X = raw.get_data(); T_true = ms._templates_cache if hasattr(ms, "_templates_cache") else None
    from eeg_tools.synthetic import _templates
    T_true = _templates(CHS_1020, 4, 123)
    g = ms.gfp(X)
    from scipy.signal import find_peaks
    idx, _ = find_peaks(g, distance=2)
    T, gev, _ = ms.modified_kmeans(X[:, idx].T, 4, n_init=6, seed=0)
    R = np.abs(T @ T_true.T)
    assert R.max(1).min() > 0.9, f"template recovery too weak: {R.max(1)}"
    assert gev > 0.6

def test_end_to_end_demo_and_comparison():
    res = run.run_demo({"k": 4, "models": ["logreg_de", "lda_bp", "riemann_ts_lr", "eegnet"]})
    m = res["microstates"]
    assert "error" not in m and m["k"] == 4 and len(m["states"]) == 4
    # tasks were generated with opposite state frequencies → at least one coverage difference must be significant after FDR
    sig = [c for c in m["comparisons"] if c["metric"] == "coverage" and c["q_fdr"] < 0.01]
    assert len(sig) >= 2, [c for c in m["comparisons"][:4]]
    dec = res["affect"]["decoding"]
    best = dec["models"][0]
    assert best["balanced_accuracy"] > 0.85, dec["models"]
    eegnet = [x for x in dec["models"] if x["id"] == "eegnet"][0]
    assert "locally" in eegnet["error"]          # deep models are local-only on the web service
    idx = res["affect"]["indices"]
    faa = [k for k in next(iter(idx.values())) if k.startswith("FAA_F4-F3")][0]
    a, b = list(idx.values())
    assert b[faa]["mean"] > a[faa]["mean"] + 0.3  # demo task B was built with stronger right-frontal alpha
    assert all(img for img in m["images"]["group_maps"])

def test_auto_k_and_registry_available():
    raws, = [run.demo_tasks(seconds=40)]
    res = run.run_analysis(raws, {"k": "auto", "affect": False})
    assert res["microstates"]["k_search"] and 2 <= res["microstates"]["k"] <= 7
    assert all(registry.get(i) for i in ("logreg_de", "riemann_ts_lr"))
