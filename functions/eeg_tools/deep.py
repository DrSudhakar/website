"""Minimal PyTorch training wrapper so braindecode architectures behave like scikit-learn classifiers (local runtime only)."""
from __future__ import annotations

import numpy as np


class BraindecodeClassifier:
    def __init__(self, arch: str, epochs: int = 40, lr: float = 1e-3, batch: int = 32, seed: int = 0):
        self.arch, self.epochs, self.lr, self.batch, self.seed = arch, epochs, lr, batch, seed

    def _prep(self, X):
        X = np.asarray(X, dtype=np.float32) * 1e6
        return (X - self.mu_) / self.sd_ if hasattr(self, "mu_") else X

    def fit(self, X, y):
        import torch
        from braindecode import models
        torch.manual_seed(self.seed)
        X = np.asarray(X, dtype=np.float32) * 1e6
        self.mu_ = X.mean((0, 2), keepdims=True); self.sd_ = X.std((0, 2), keepdims=True) + 1e-6
        Xs = torch.tensor((X - self.mu_) / self.sd_); ys = torch.tensor(np.asarray(y), dtype=torch.long)
        self.classes_ = np.unique(y)
        cls = getattr(models, self.arch)
        self.net_ = cls(n_chans=X.shape[1], n_outputs=len(self.classes_), n_times=X.shape[2])
        opt = torch.optim.AdamW(self.net_.parameters(), lr=self.lr, weight_decay=1e-3)
        loss_fn = torch.nn.CrossEntropyLoss()
        self.net_.train()
        for _ in range(self.epochs):
            perm = torch.randperm(len(Xs))
            for i in range(0, len(perm), self.batch):
                idx = perm[i:i + self.batch]
                if len(idx) < 2:
                    continue
                opt.zero_grad(); loss = loss_fn(self.net_(Xs[idx]), ys[idx]); loss.backward(); opt.step()
        return self

    def predict(self, X):
        import torch
        self.net_.eval()
        with torch.no_grad():
            Xs = torch.tensor(((np.asarray(X, dtype=np.float32) * 1e6) - self.mu_) / self.sd_)
            out = torch.cat([self.net_(Xs[i:i + 128]) for i in range(0, len(Xs), 128)])
        return self.classes_[out.argmax(1).numpy()]
