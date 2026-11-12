"""Registry of open-source EEG models that the lab site can run.

runtime = "function": runs on the Firebase web service (scikit-learn / pyriemann, CPU, seconds).
runtime = "local"   : needs PyTorch (braindecode) — listed and smoke-tested weekly, run with  python -m eeg_tools.cli.

scripts/test_eeg_models.py builds every model here on synthetic data and checks that it (a) runs and (b) beats chance.
Add a model = add one entry (and, if it needs a new library, add it to requirements)."""
from __future__ import annotations

import importlib
import importlib.util


def _sk(name, seed):
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    return {
        "logreg_de": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000)),
        "svm_rbf_de": lambda: make_pipeline(StandardScaler(), SVC(C=1.0, kernel="rbf", gamma="scale")),
        "rf_de": lambda: RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1),
        "lda_bp": lambda: make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
        "hgb_bp": lambda: HistGradientBoostingClassifier(max_iter=100, min_samples_leaf=3, early_stopping=False, random_state=seed),
    }[name]()


def _riemann(seed):
    from pyriemann.estimation import Covariances
    from pyriemann.tangentspace import TangentSpace
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(Covariances(estimator="oas"), TangentSpace(metric="riemann"), LogisticRegression(C=1.0, max_iter=3000))


def _deep(arch):
    def build(seed, n_chans=None, n_times=None, n_outputs=2):
        from .deep import BraindecodeClassifier
        return BraindecodeClassifier(arch, seed=seed)
    return build


MODELS = [
    {"id": "logreg_de", "name": "Logistic regression · differential entropy", "family": "linear", "runtime": "function", "input": "de", "requires": ["sklearn"], "build": lambda s: _sk("logreg_de", s),
     "description": "Standard baseline for SEED-style emotion recognition: DE features per band and channel, L2-regularised logistic regression.", "source": "scikit-learn"},
    {"id": "svm_rbf_de", "name": "SVM (RBF) · differential entropy", "family": "kernel", "runtime": "function", "input": "de", "requires": ["sklearn"], "build": lambda s: _sk("svm_rbf_de", s),
     "description": "Widely used non-linear baseline for EEG emotion recognition.", "source": "scikit-learn"},
    {"id": "rf_de", "name": "Random forest · differential entropy", "family": "ensemble", "runtime": "function", "input": "de", "requires": ["sklearn"], "build": lambda s: _sk("rf_de", s),
     "description": "Tree ensemble on DE features; robust to feature scaling and gives a non-linear reference.", "source": "scikit-learn"},
    {"id": "lda_bp", "name": "Shrinkage LDA · log band power", "family": "linear", "runtime": "function", "input": "bp", "requires": ["sklearn"], "build": lambda s: _sk("lda_bp", s),
     "description": "Classic BCI classifier (regularised LDA) on spectral band power.", "source": "scikit-learn"},
    {"id": "hgb_bp", "name": "Gradient boosting · log band power", "family": "ensemble", "runtime": "function", "input": "bp", "requires": ["sklearn"], "build": lambda s: _sk("hgb_bp", s),
     "description": "Histogram gradient boosting (LightGBM-style) on band power.", "source": "scikit-learn"},
    {"id": "riemann_ts_lr", "name": "Riemannian tangent space + LR", "family": "riemannian", "runtime": "function", "input": "epochs", "requires": ["pyriemann", "sklearn"], "build": _riemann,
     "description": "Covariance matrices → tangent space → logistic regression. A strong, training-light state-of-the-art baseline in EEG decoding.", "source": "pyRiemann"},
    {"id": "eegnet", "name": "EEGNet (braindecode)", "family": "deep-cnn", "runtime": "local", "input": "epochs", "requires": ["torch", "braindecode"], "arch": "EEGNet", "build": _deep("EEGNet"),
     "description": "Compact CNN for EEG (Lawhern et al., 2018).", "source": "braindecode"},
    {"id": "shallow_convnet", "name": "ShallowFBCSPNet (braindecode)", "family": "deep-cnn", "runtime": "local", "input": "epochs", "requires": ["torch", "braindecode"], "arch": "ShallowFBCSPNet", "build": _deep("ShallowFBCSPNet"),
     "description": "Shallow ConvNet inspired by filter-bank CSP (Schirrmeister et al., 2017).", "source": "braindecode"},
    {"id": "eeg_conformer", "name": "EEG Conformer (braindecode)", "family": "deep-transformer", "runtime": "local", "input": "epochs", "requires": ["torch", "braindecode"], "arch": "EEGConformer", "build": _deep("EEGConformer"),
     "description": "CNN + self-attention transformer for EEG (Song et al., 2023).", "source": "braindecode"},
]
_BY_ID = {m["id"]: m for m in MODELS}


def get(model_id: str):
    return _BY_ID.get(model_id)


def is_available(spec) -> tuple[bool, str]:
    for mod in spec["requires"]:
        if importlib.util.find_spec(mod) is None:
            return False, f"python package '{mod}' is not installed"
    return True, ""
