"""Dwell models (C4 §6): L0 historical median and L1 LightGBM quantiles with conformal intervals.

Target: log dwell hours at arrival (D-04: anchorage wait + berth time). L0 is the empirical
P10/P50/P90 by ship type × flag × month, backing off to coarser groups. L1 fits three LightGBM
quantile models (P10, P50, P90) and MAPIE conformalises the P10–P90 band on a later validation
window (CQR), so the 80 % interval holds its coverage out of time. Drivers are TreeSHAP
contributions of the P50 model (LightGBM `pred_contrib`), read as % change in dwell.

The split is by arrival time: train < validate < gap < test. The test window ends
`censor_gap_days` before the data does (GFW publishes only finished visits, so the latest
arrivals are biased short), and train and validation end the same gap before the test window,
with only labels known by then.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor
from mapie.regression import ConformalizedQuantileRegressor
from numpy.typing import NDArray

from cportal_c4.config import load_config
from cportal_c4.features import LABELS, NAMES, describe
from cportal_c4.labels import Calls

DAY = 24.0
Bands = tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]


@dataclass
class Split:
    train: NDArray[np.bool_]
    val: NDArray[np.bool_]
    test: NDArray[np.bool_]
    bounds: dict[str, float]


def split(calls: Calls, keep: NDArray[np.bool_], since_h: float | None = None) -> Split:
    """Train and validation labels must be known when the test window opens, so both end a
    censoring gap earlier (a 45-day gap leaves almost every label complete, not just short ones).
    """
    cfg = load_config()["split"]
    gap = float(cfg["censor_gap_days"]) * DAY
    end = float(np.nanmax(calls.arrival)) - gap
    test_start = end - float(cfg["test_days"]) * DAY
    val_end = test_start - gap
    val_start = val_end - float(cfg["validate_days"]) * DAY
    a, d = calls.arrival, calls.departure
    base = keep & (a >= since_h if since_h is not None else True)
    known = d < test_start
    return Split(
        train=base & known & (a < val_start),
        val=base & known & (a >= val_start) & (a < val_end),
        test=base & (a >= test_start) & (a < end),
        bounds={
            "val_start": val_start,
            "val_end": val_end,
            "test_start": test_start,
            "test_end": end,
        },
    )


class Baseline:
    """L0: empirical P10/P50/P90 of dwell by (type, flag, month), backing off when thin."""

    MIN = 30

    def fit(self, calls: Calls, X: NDArray[np.float64], mask: NDArray[np.bool_]) -> Baseline:
        groups: dict[tuple[Any, ...], list[float]] = defaultdict(list)
        month = X[:, NAMES.index("month")]
        for i in np.flatnonzero(mask):
            for key in self._keys(calls.group[i], bool(calls.domestic[i]), int(month[i])):
                groups[key].append(float(calls.dwell[i]))
        self.table = {
            k: tuple(float(q) for q in np.percentile(v, [10, 50, 90]))
            for k, v in groups.items()
            if len(v) >= self.MIN
        }
        return self

    @staticmethod
    def _keys(group: str, domestic: bool, month: int) -> list[tuple[Any, ...]]:
        return [(group, domestic, month), (group, domestic), (group,), ()]

    def predict(self, calls: Calls, X: NDArray[np.float64]) -> Bands:
        month = X[:, NAMES.index("month")]
        out = np.zeros((len(calls), 3))
        for i in range(len(calls)):
            for key in self._keys(calls.group[i], bool(calls.domestic[i]), int(month[i])):
                if key in self.table:
                    out[i] = self.table[key]
                    break
        return out[:, 0], out[:, 1], out[:, 2]


class QuantileModel:
    """L1: LightGBM P10/P50/P90 on log dwell, P10–P90 conformalised with MAPIE (CQR)."""

    def __init__(self, seed: int = 7) -> None:
        cfg = load_config()["model"]
        self.level = float(cfg["interval"])
        lo, hi = (1 - self.level) / 2, 1 - (1 - self.level) / 2
        params: dict[str, Any] = {
            "objective": "quantile",
            "n_estimators": 400,
            "learning_rate": 0.04,
            "num_leaves": 31,
            "min_child_samples": 40,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
            "random_state": seed,
            "verbose": -1,
        }
        self.models = [LGBMRegressor(alpha=a, **params) for a in (lo, hi, 0.5)]

    def fit(
        self,
        X: NDArray[np.float64],
        y_h: NDArray[np.float64],
        X_val: NDArray[np.float64],
        y_val_h: NDArray[np.float64],
    ) -> QuantileModel:
        y = np.log(y_h)
        for m in self.models:
            m.fit(X, y)
        self.cqr = ConformalizedQuantileRegressor(
            self.models, confidence_level=self.level, prefit=True
        )
        self.cqr.conformalize(X_val, np.log(y_val_h))
        return self

    def predict(self, X: NDArray[np.float64]) -> Bands:
        p50, pis = self.cqr.predict_interval(X)
        lo, hi = pis[:, 0, 0], pis[:, 1, 0]
        p50 = np.clip(p50, lo, hi)
        return np.exp(lo), np.exp(p50), np.exp(hi)

    def drivers(self, X: NDArray[np.float64], top: int = 3) -> list[list[dict[str, Any]]]:
        """Top TreeSHAP contributions of the P50 model, as % change in dwell."""
        contrib = np.asarray(self.models[2].predict(X, pred_contrib=True))[:, :-1]
        out = []
        for row, values in zip(contrib, X, strict=True):
            order = np.argsort(-np.abs(row))[:top]
            out.append(
                [
                    {
                        "feature": NAMES[j],
                        "label": LABELS[NAMES[j]],
                        "value": describe(NAMES[j], float(values[j])),
                        "effect_pct": round(float(np.expm1(row[j])) * 100, 1),
                    }
                    for j in order
                ]
            )
        return out


def score(y: NDArray[np.float64], bands: Bands) -> dict[str, float]:
    p10, p50, p90 = bands
    q = [(0.1, p10), (0.5, p50), (0.9, p90)]
    pinball = np.mean(
        [np.mean(np.maximum(a * (y - p), (a - 1) * (y - p))) for a, p in q]
    )  # fmt: skip
    return {
        "n": len(y),
        "mae_h": round(float(np.mean(np.abs(y - p50))), 2),
        "median_ape": round(float(np.median(np.abs(y - p50) / y)), 3),
        "coverage_80": round(float(np.mean((y >= p10) & (y <= p90))), 3),
        "width_h": round(float(np.median(p90 - p10)), 1),
        "pinball_h": round(float(pinball), 2),
    }
