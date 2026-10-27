"""Remaining time in port for vessels already there (C4 §6 L2, C4-R03, C4-AC05).

A random survival forest (scikit-survival) learns the dwell distribution S(t | x) from the
arrival features; for a vessel `e` hours in, the remaining-time quantiles solve
S(e + r) / S(e) = 1 - q, so the answer moves as time passes. The baseline is the same
conditioning on a Kaplan–Meier curve with no covariates. Times are binned to 2 h to keep the
forest small; active calls enter as censored at their elapsed time.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray
from sksurv.ensemble import RandomSurvivalForest
from sksurv.metrics import concordance_index_censored, integrated_brier_score
from sksurv.nonparametric import kaplan_meier_estimator
from sksurv.util import Surv

BIN_H = 2.0
QUANTILES = (0.1, 0.5, 0.9)


def _clean(X: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.nan_to_num(X, nan=-1.0)


def remaining(
    times: NDArray[np.float64], surv: NDArray[np.float64], elapsed: float
) -> tuple[float, float, float]:
    """Remaining-hour quantiles from one survival curve, given the hours already spent."""
    s_e = float(np.interp(elapsed, times, surv, left=1.0, right=float(surv[-1])))
    later = times > elapsed
    if s_e <= 1e-9 or not later.any():
        return (0.0, 0.0, 0.0)
    cond = surv[later] / s_e
    out = []
    for q in QUANTILES:
        hit = np.flatnonzero(cond <= 1 - q)
        t = times[later][hit[0]] if len(hit) else times[-1]
        out.append(max(float(t) - elapsed, 0.0))
    return out[0], out[1], out[2]


class RemainingModel:
    def __init__(self, max_samples: int = 10_000, seed: int = 0) -> None:
        self.max_samples = max_samples
        self.seed = seed
        self.forest = RandomSurvivalForest(
            n_estimators=100, min_samples_leaf=40, max_features="sqrt", n_jobs=4, random_state=seed
        )

    def fit(
        self, X: NDArray[np.float64], dwell: NDArray[np.float64], event: NDArray[np.bool_]
    ) -> RemainingModel:
        rng = np.random.default_rng(self.seed)
        idx = np.arange(len(dwell))
        if len(idx) > self.max_samples:
            idx = rng.choice(idx, self.max_samples, replace=False)
        t = np.ceil(dwell[idx] / BIN_H) * BIN_H
        self.train_y = Surv.from_arrays(event[idx], t)
        self.forest.fit(_clean(X[idx]), self.train_y)
        self.times = np.asarray(self.forest.unique_times_, dtype=np.float64)
        km_t, km_s = kaplan_meier_estimator(event[idx], t)
        self.km = (np.asarray(km_t, dtype=np.float64), np.asarray(km_s, dtype=np.float64))
        return self

    def curves(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(self.forest.predict_survival_function(_clean(X), return_array=True))

    def predict(
        self, X: NDArray[np.float64], elapsed: NDArray[np.float64]
    ) -> list[tuple[float, float, float]]:
        return [
            remaining(self.times, s, float(e)) for s, e in zip(self.curves(X), elapsed, strict=True)
        ]

    def baseline(self, elapsed: NDArray[np.float64]) -> list[tuple[float, float, float]]:
        return [remaining(*self.km, float(e)) for e in elapsed]

    def evaluate(
        self, X: NDArray[np.float64], dwell: NDArray[np.float64], event: NDArray[np.bool_]
    ) -> dict[str, Any]:
        """C-index and integrated Brier score on held-out calls, against Kaplan–Meier."""
        test_y = Surv.from_arrays(event, dwell)
        cindex = concordance_index_censored(event, dwell, self.forest.predict(_clean(X)))[0]
        lo, hi = np.percentile(dwell[event], [10, 85])
        grid = np.linspace(lo, hi, 20)
        grid = grid[(grid > self.times[0]) & (grid < self.times[-1])]
        at = np.searchsorted(self.times, grid, "right") - 1
        ibs = integrated_brier_score(self.train_y, test_y, self.curves(X)[:, at], grid)
        km_at = np.searchsorted(self.km[0], grid, "right") - 1
        km = np.tile(self.km[1][np.maximum(km_at, 0)], (len(dwell), 1))
        ibs_km = integrated_brier_score(self.train_y, test_y, km, grid)
        return {
            "n": len(dwell),
            "c_index": round(float(cindex), 3),
            "ibs": round(float(ibs), 4),
            "ibs_kaplan_meier": round(float(ibs_km), 4),
        }
