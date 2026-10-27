"""Train, evaluate and replay C4 for one port (`uv run c4 train BDCGP`).

One backtest per run: models see only labels known when the test window opens, are scored on
it (C4-AC03…AC06), and the same models make the replay snapshots inside that window, so what
the Ports page shows was predictable at the time (with the actual outcome alongside).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.orm import Session

from cportal_c4.config import load_config
from cportal_c4.features import FeatureBuilder
from cportal_c4.forecast import QueueForecaster, backtest, daily_series
from cportal_c4.labels import Calls, hours, label_mask, load_calls, load_presence, to_ts
from cportal_c4.model import Baseline, QuantileModel, Split, score, split
from cportal_c4.survival import RemainingModel

SNAPSHOT_HOUR_UTC = 6  # 12:00 in Dhaka
MIN_TRAIN, MIN_VAL = 1000, 100


class NotEnoughHistory(ValueError):
    """Too few labelled calls for the split (run `uv run gfw-backfill` first)."""


@dataclass
class Run:
    locode: str
    calls: Calls
    presence: dict[date, float]
    X: NDArray[np.float64]
    keep: NDArray[np.bool_]
    split: Split
    baseline: Baseline
    dwell: QuantileModel
    remaining: RemainingModel
    queue: QueueForecaster | None
    series: tuple[list[date], NDArray[np.float64]] | None
    report: dict[str, Any]


def train(session: Session, locode: str, ablation: bool = True) -> Run:
    cfg = load_config()
    t0 = time.perf_counter()
    calls = load_calls(session, locode, real_only=True)
    area = cfg["features"]["presence_area"].get(locode)
    presence = load_presence(session, area) if area else {}
    lag = float(cfg["features"]["visibility_lag_h"])
    keep, labels = label_mask(calls)
    since = hours(datetime.fromisoformat(cfg["split"]["since"]).replace(tzinfo=UTC))
    sp = split(calls, keep, since)
    if sp.train.sum() < MIN_TRAIN or sp.val.sum() < MIN_VAL or not sp.test.any():
        raise NotEnoughHistory(
            f"{locode}: {int(sp.train.sum())} train / {int(sp.val.sum())} validation calls; "
            "run `uv run gfw-backfill`"
        )
    y = calls.dwell
    cargo = sp.test & (calls.group == "cargo")

    def fit(lag_h: float) -> tuple[NDArray[np.float64], Baseline, QuantileModel, dict[str, Any]]:
        X = FeatureBuilder(calls, presence, lag_h).matrix(calls)
        base = Baseline().fit(calls, X, sp.train | sp.val)
        model = QuantileModel().fit(X[sp.train], y[sp.train], X[sp.val], y[sp.val])
        b, q = base.predict(calls, X), model.predict(X)
        scores = {
            f"{name}_{pop}": score(y[m], (bands[0][m], bands[1][m], bands[2][m]))
            for name, bands in (("L0", b), ("L1", q))
            for pop, m in (("all", sp.test), ("cargo", cargo))
        }
        return X, base, model, scores

    X, base, model, dwell_scores = fit(lag)
    report: dict[str, Any] = {
        "port": locode,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "labels": labels,
        "split": {k: to_ts(v).date().isoformat() for k, v in sp.bounds.items()}
        | {"train": int(sp.train.sum()), "val": int(sp.val.sum()), "test": int(sp.test.sum())},
        "visibility_lag_h": lag,
        "dwell": dwell_scores,
    }
    for pop in ("all", "cargo"):
        l0, l1 = dwell_scores[f"L0_{pop}"]["mae_h"], dwell_scores[f"L1_{pop}"]["mae_h"]
        report["dwell"][f"mae_gain_{pop}"] = round(1 - l1 / l0, 3)
    if ablation:  # what the feed's latency costs (C4 §5)
        report["lag_ablation"] = {
            str(int(other)): fit(other)[3]["L1_cargo"] for other in (0.0, 96.0) if other != lag
        }
    # L2: remaining time, trained on the same labels; scored on the test calls.
    train_mask = sp.train | sp.val
    remaining = RemainingModel().fit(X[train_mask], y[train_mask], np.ones(train_mask.sum(), bool))
    report["remaining"] = remaining.evaluate(X[sp.test], y[sp.test], np.ones(sp.test.sum(), bool))
    report["remaining"] |= _landmark(remaining, X, calls, sp.test)
    # L3: anchorage queue (only where GFW presence exists).
    queue, series = None, None
    if presence:
        days, values = daily_series(presence)
        series = (days, values)
        test_start = to_ts(sp.bounds["test_start"]).date()
        end = days.index(test_start) if test_start in days else len(days) - 1
        queue = QueueForecaster().fit(days, values, end)
        report["queue"] = backtest(days, values, test_days=120, horizon=7)
    report["seconds"] = round(time.perf_counter() - t0, 1)
    return Run(locode, calls, presence, X, keep, sp, base, model, remaining, queue, series, report)


def _landmark(
    model: RemainingModel, X: NDArray[np.float64], calls: Calls, test: NDArray[np.bool_]
) -> dict[str, Any]:
    """Remaining-time error for test vessels still in port 24 h after arrival, vs Kaplan–Meier."""
    e = 24.0
    idx = np.flatnonzero(test & (calls.dwell > e))
    actual = calls.dwell[idx] - e
    rsf = np.array([p[1] for p in model.predict(X[idx], np.full(len(idx), e))])
    km = np.array([p[1] for p in model.baseline(np.full(len(idx), e))])
    return {
        "landmark_h": e,
        "landmark_n": len(idx),
        "remaining_mae_h": round(float(np.mean(np.abs(actual - rsf))), 1),
        "remaining_mae_h_kaplan_meier": round(float(np.mean(np.abs(actual - km))), 1),
    }


def snapshots(run: Run) -> list[datetime]:
    """Replay times: noon in Dhaka on each day of the test window."""
    start = to_ts(run.split.bounds["test_start"]).date()
    end = to_ts(run.split.bounds["test_end"]).date()
    out, d = [], start
    while d < end:
        out.append(datetime(d.year, d.month, d.day, SNAPSHOT_HOUR_UTC, tzinfo=UTC))
        d += timedelta(days=1)
    return out
