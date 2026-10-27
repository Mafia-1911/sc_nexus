"""Port-level queue forecast, 1–14 days (C4 §6 L3, C4-R02, C4-AC06).

Series: vessels in the outer anchorage per day (GFW 4Wings presence, ≥ 1 h). Baseline:
seasonal naive (same weekday last week) with empirical residual quantiles per horizon.
Candidate: direct LightGBM P50 models, one per horizon, on lags, rolling means, weekday and
month, with conformal P10/P90 from a 90-day calibration window. Both are scored by rolling
origin over the last `test_days`: MASE against the in-sample seasonal-naive scale and the
weighted quantile loss (WQL) over P10/P50/P90.
A time-series foundation model (Chronos-2) is the next rung; it is run offline (D-03).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor
from numpy.typing import NDArray

H = 14
SEASON = 7
QS = (0.1, 0.5, 0.9)
LAGS = (0, 1, 2, 3, 6, 13, 27)


def daily_series(presence: dict[date, float]) -> tuple[list[date], NDArray[np.float64]]:
    """A gap-free daily series; missing days are filled from the day before."""
    days = sorted(presence)
    out_days, values = [], []
    d, last = days[0], presence[days[0]]
    while d <= days[-1]:
        last = presence.get(d, last)
        out_days.append(d)
        values.append(last)
        d += timedelta(days=1)
    return out_days, np.array(values, dtype=np.float64)


def _features(y: NDArray[np.float64], days: list[date], t: int, h: int) -> list[float]:
    target = days[t] + timedelta(days=h)
    return [
        *(y[t - k] for k in LAGS),
        float(np.mean(y[t - 6 : t + 1])),
        float(np.mean(y[t - 27 : t + 1])),
        float(np.std(y[t - 27 : t + 1])),
        float(target.weekday()),
        float(target.month),
    ]


def seasonal_naive(y: NDArray[np.float64], t: int, h: int) -> float:
    return float(y[t + h - SEASON * int(np.ceil(h / SEASON))])


class QueueForecaster:
    """Direct LightGBM P50 per horizon; P10/P90 from residual quantiles on a later calibration
    window (split conformal), since quantile trees alone gave bands that were far too narrow."""

    def fit(
        self, days: list[date], y: NDArray[np.float64], end: int, cal_days: int = 90
    ) -> QueueForecaster:
        start, fit_end = max(LAGS) + 1, end - cal_days
        self.models: dict[int, LGBMRegressor] = {}
        self.resid: dict[int, NDArray[np.float64]] = {}
        for h in range(1, H + 1):
            ts = range(start, fit_end - h)
            X = np.array([_features(y, days, t, h) for t in ts])
            m = LGBMRegressor(
                objective="quantile", alpha=0.5, n_estimators=200, learning_rate=0.05,
                num_leaves=15, min_child_samples=20, random_state=7, verbose=-1,
            )  # fmt: skip
            self.models[h] = m.fit(X, np.array([y[t + h] for t in ts]))
            cal = range(fit_end, end - h)
            Xc = np.array([_features(y, days, t, h) for t in cal])
            err = np.array([y[t + h] for t in cal]) - m.predict(Xc)
            self.resid[h] = np.percentile(err, [QS[0] * 100, QS[2] * 100])
        return self

    def predict(self, days: list[date], y: NDArray[np.float64], t: int) -> NDArray[np.float64]:
        """(H, 3) array: P10/P50/P90 for t+1 … t+H."""
        out = np.zeros((H, len(QS)))
        for h in range(1, H + 1):
            p50 = float(self.models[h].predict(np.array([_features(y, days, t, h)]))[0])
            lo, hi = self.resid[h]
            out[h - 1] = (p50 + min(lo, 0.0), p50, p50 + max(hi, 0.0))
        return out


def _wql(y: NDArray[np.float64], pred: NDArray[np.float64]) -> float:
    loss = sum(
        np.sum(np.maximum(q * (y - pred[:, i]), (q - 1) * (y - pred[:, i])))
        for i, q in enumerate(QS)
    )
    return float(2 * loss / (len(QS) * np.sum(np.abs(y))))


def backtest(
    days: list[date], y: NDArray[np.float64], test_days: int = 120, horizon: int = 7
) -> dict[str, Any]:
    """Rolling origin over the last `test_days`; MASE and WQL at `horizon` days ahead."""
    end = len(y) - test_days
    model = QueueForecaster().fit(days, y, end)
    scale = float(np.mean(np.abs(y[SEASON:end] - y[: end - SEASON])))
    # Seasonal-naive residual quantiles per horizon, from the training period.
    resid = {
        h: np.percentile(
            [y[t + h] - seasonal_naive(y, t, h) for t in range(SEASON, end - h)],
            [q * 100 for q in QS],
        )
        for h in range(1, H + 1)
    }
    rows = []
    for t in range(end, len(y) - horizon):
        naive = seasonal_naive(y, t, horizon) + resid[horizon]
        rows.append((y[t + horizon], naive, model.predict(days, y, t)[horizon - 1]))
    actual = np.array([r[0] for r in rows])
    naive_p = np.array([r[1] for r in rows])
    model_p = np.array([r[2] for r in rows])
    return {
        "origins": len(rows),
        "horizon_d": horizon,
        "seasonal_naive": {
            "mase": round(float(np.mean(np.abs(actual - naive_p[:, 1])) / scale), 3),
            "wql": round(_wql(actual, naive_p), 4),
        },
        "lightgbm": {
            "mase": round(float(np.mean(np.abs(actual - model_p[:, 1])) / scale), 3),
            "wql": round(_wql(actual, model_p), 4),
            "coverage_80": round(
                float(np.mean((actual >= model_p[:, 0]) & (actual <= model_p[:, 2]))), 3
            ),
        },
    }
