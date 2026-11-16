"""A-122: the berth-wait model's live features and its stored form (no database)."""

from __future__ import annotations

import numpy as np
from cportal_c4.waits import WaitModel, features_at


def test_queue_and_alongside_at_a_moment() -> None:
    arrival = np.array([0.0, 2.0, 5.0, 9.0])
    berthed = np.array([1.0, 8.0, 6.0, 12.0])
    left = np.array([40.0, 30.0, 7.0, 50.0])
    # At t = 5.5: ships 1 and 2 still wait (berth at 8 and 6); ship 0 is alongside.
    assert features_at(5.5, arrival, berthed, left) == (2, 1)
    assert features_at(0.5, arrival, berthed, left) == (1, 0)


def test_model_round_trips_and_orders_its_bands() -> None:
    rng = np.random.default_rng(3)
    X = np.column_stack([rng.integers(0, 15, 600), rng.integers(10, 30, 600),
                         rng.integers(0, 24, 600), rng.integers(0, 7, 600),
                         rng.integers(1, 13, 600)]).astype(float)  # fmt: skip
    y = np.exp(0.15 * X[:, 0]) + rng.exponential(2.0, 600)  # longer queue, longer wait
    m = WaitModel().fit(X[:400], y[:400], X[400:], y[400:])
    again = WaitModel.load(m.dump())
    lo, mid, hi = again.predict(X[:50])
    assert np.allclose(mid, m.predict(X[:50])[1])
    assert np.all(lo <= mid) and np.all(mid <= hi) and np.all(lo >= 0)
    short, long = again.predict(np.array([[1, 20, 10, 2, 6], [14, 20, 10, 2, 6]], dtype=float))[1]
    assert long > short
