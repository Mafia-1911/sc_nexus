"""C4 on hand-made calls (no database): leakage, feature arithmetic, split, models."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import numpy as np
import pytest
from cportal_c4.features import NAMES, FeatureBuilder, truncate
from cportal_c4.labels import Calls, label_mask
from cportal_c4.model import Baseline, QuantileModel, score, split


def make_calls(n: int = 3000, seed: int = 1) -> Calls:
    """A port where dwell grows with the queue and repeat callers keep their habits."""
    rng = np.random.default_rng(seed)
    arrival = np.sort(rng.uniform(0, 24 * 400, n)) + 480_000.0  # hours since epoch (≈ 2024)
    mmsi = rng.integers(0, 600, n) + 400_000_000
    habit = 40 + (mmsi % 7) * 15.0
    recent = np.searchsorted(arrival, arrival) - np.searchsorted(arrival, arrival - 72)
    load = 0.5 + recent / max(float(recent.mean()), 1.0)
    season = 1 + 0.5 * np.sin(2 * np.pi * arrival / (24 * 60))
    dwell = habit * load * season * rng.lognormal(0, 0.35, n) + 3
    departure = arrival + dwell
    departure[-40:] = np.nan  # still in port at the end
    return Calls(
        ids=[uuid4() for _ in range(n)],
        vessel_ids=[uuid4() for _ in range(n)],
        mmsi=mmsi.astype(np.int64),
        group=np.where(rng.random(n) < 0.8, "cargo", "unknown").astype(np.str_),
        domestic=rng.random(n) < 0.2,
        arrival=arrival,
        departure=departure,
        confidence=np.full(n, 4, dtype=np.int64),
        flags=[[] for _ in range(n)],
        synthetic=np.ones(n, dtype=np.bool_),
    )


def presence_for(calls: Calls) -> dict[date, float]:
    days = np.unique((calls.arrival // 24).astype(int))
    return {date.fromordinal(date(1970, 1, 1).toordinal() + int(d)): 50.0 + d % 9 for d in days}


@pytest.mark.parametrize("lag", [0.0, 24.0, 96.0])
def test_features_never_read_past_as_of(lag: float) -> None:
    """C4-AC07: features from the full history equal those from what was known at `as_of`."""
    calls = make_calls()
    presence = presence_for(calls)
    full = FeatureBuilder(calls, presence, lag).matrix(calls)
    for i in np.random.default_rng(3).choice(len(calls), 60, replace=False):
        t = float(calls.arrival[i]) - lag
        seen = truncate(calls, t)
        seen_presence = {
            d: v for d, v in presence.items() if (d.toordinal() - 719163 + 1) * 24 <= t
        }
        target = calls.take(np.arange(len(calls)) == i)
        past = FeatureBuilder(seen, seen_presence, lag).matrix(target)[0]
        np.testing.assert_array_equal(full[i], past, err_msg=f"call {i}")


def test_leakage_test_catches_a_leak() -> None:
    """The check above would fail if a feature used the vessel's own future departure."""
    calls = make_calls(500)
    X = FeatureBuilder(calls, None, 0).matrix(calls)
    leaky = np.column_stack([X, calls.departure - calls.arrival])
    seen = truncate(calls, float(calls.arrival[250]))
    target = calls.take(np.arange(len(calls)) == 250)
    honest = FeatureBuilder(seen, None, 0).matrix(target)[0]
    leaked = np.append(honest, seen.departure[-1] - seen.arrival[-1] if len(seen) else np.nan)
    assert not np.array_equal(leaky[250], leaked, equal_nan=True)


def test_queue_counts_by_hand() -> None:
    calls = make_calls(10)
    calls.arrival = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=np.float64) + 1000
    calls.departure = calls.arrival + np.array([1.5, 10, 10, 0.5, 100, 2000, 3, 3, 3, np.nan])
    X = FeatureBuilder(calls, None, 0).matrix(calls, as_of=np.full(10, 1006.0))
    n = X[0, NAMES.index("n_present")]
    # Before t = 1006: arrived 0..5; departed 0 (1001.5) and 3 (1003.5); 5 is laid up but has
    # been there < 60 days, so it still counts.
    assert n == 4
    assert X[0, NAMES.index("arrivals_24h")] == 6
    assert X[0, NAMES.index("departures_24h")] == 2


def test_labels_and_split_are_time_ordered() -> None:
    calls = make_calls()
    keep, info = label_mask(calls)
    assert info["dropped"]["active (censored)"] == 40 and info["kept"] == int(keep.sum())
    sp = split(calls, keep)
    assert calls.arrival[sp.train].max() < calls.arrival[sp.val].min()
    assert calls.arrival[sp.val].max() < calls.arrival[sp.test].min()
    assert np.all(calls.departure[sp.train | sp.val] < sp.bounds["test_start"])


def test_quantile_model_beats_the_median_and_covers() -> None:
    calls = make_calls(4000)
    keep, _ = label_mask(calls)
    sp = split(calls, keep)
    X = FeatureBuilder(calls, presence_for(calls), 24).matrix(calls)
    y = calls.dwell
    l0 = Baseline().fit(calls, X, sp.train | sp.val).predict(calls, X)
    l1 = QuantileModel().fit(X[sp.train], y[sp.train], X[sp.val], y[sp.val])
    b0 = score(y[sp.test], tuple(b[sp.test] for b in l0))
    b1 = score(y[sp.test], tuple(b[sp.test] for b in l1.predict(X)))
    assert b1["mae_h"] < 0.85 * b0["mae_h"]
    assert 0.65 <= b1["coverage_80"] <= 0.95
    drivers = l1.drivers(X[:2])
    assert len(drivers[0]) == 3
    assert {"feature", "label", "value", "effect_pct"} <= set(drivers[0][0])
