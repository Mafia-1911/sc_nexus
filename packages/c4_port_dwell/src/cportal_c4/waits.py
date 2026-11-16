"""C4 berth-wait model (A-122): how long a container ship waits at the anchorage at Chattogram.

Labels: the GFW + CPA split (`service.berth_split`: wait = CPA berthing - GFW arrival), 2023 on.
Features are those CPA shows live at the moment a ship arrives, so training and serving match:
container ships already waiting, ships alongside, hour, weekday and month (Dhaka). Model:
LightGBM P10/P50/P90 on log1p(wait), the P10-P90 band widened by split conformal (CQR) on a
validation period. Baseline: the empirical P10/P50/P90 of the waits of ships that berthed in
the 30 days before arrival (what the Ships table used). Time-based holdout; the model is marked
active only if it beats the baseline's pinball loss on the test period (AGENTS rule 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import numpy as np
from cportal_core.models import ModelVersion
from lightgbm import Booster, LGBMRegressor
from numpy.typing import NDArray
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cportal_c4 import service
from cportal_c4.model import score

NAME = "c4-berth-wait"
VERSION = "0.1.0"
FEATURES = ["queue", "at_berth", "hour", "dow", "month"]
DHAKA = timezone(timedelta(hours=6))
QUANTILES = (0.1, 0.9, 0.5)
LEVEL = 0.8
SPLITS = {
    "train_until": datetime(2025, 7, 1, tzinfo=UTC),
    "test_from": datetime(2026, 1, 1, tzinfo=UTC),
}


@dataclass
class Table:
    arrival: NDArray[np.float64]  # hours since epoch
    berthed: NDArray[np.float64]
    left: NDArray[np.float64]
    wait: NDArray[np.float64]
    X: NDArray[np.float64]


def _h(ts: datetime) -> float:
    return ts.timestamp() / 3600


def features_at(t: float, arrival: NDArray[np.float64], berthed: NDArray[np.float64],
                left: NDArray[np.float64]) -> tuple[int, int]:  # fmt: skip
    """Ships waiting (arrived, not yet berthed) and alongside (berthed, not left) at time t."""
    queue = int(np.sum((arrival < t) & (berthed > t)))
    at_berth = int(np.sum((berthed <= t) & (left > t)))
    return queue, at_berth


def calendar(ts: datetime) -> list[float]:
    d = ts.astimezone(DHAKA)
    return [float(d.hour), float(d.weekday()), float(d.month)]


def table(session: Session, locode: str = "BDCGP") -> Table:
    rows = service.berth_split(session, locode, datetime(2023, 1, 1, tzinfo=UTC), datetime.now(UTC))
    rows.sort(key=lambda r: r[0])
    arrival = np.array([_h(a) for a, *_ in rows])
    wait = np.array([w for _, w, _, _ in rows])
    berthed = arrival + wait
    left = berthed + np.array([b for *_, b, _ in rows])
    X = np.array([
        [*features_at(arrival[i], arrival, berthed, left), *calendar(rows[i][0])]
        for i in range(len(rows))
    ])  # fmt: skip
    return Table(arrival, berthed, left, wait, X)


def baseline(t: Table, idx: NDArray[np.intp], days: int = 30) -> tuple[NDArray[np.float64], ...]:
    """Rolling empirical quantiles of the waits of ships that berthed in the previous `days`."""
    out = np.zeros((len(idx), 3))
    for k, i in enumerate(idx):
        now = t.arrival[i]
        past = t.wait[(t.berthed < now) & (t.berthed >= now - days * 24)]
        out[k] = np.quantile(past, [0.1, 0.5, 0.9]) if len(past) >= 10 else np.nan
    return out[:, 0], out[:, 1], out[:, 2]


class WaitModel:
    """Three LightGBM quantile boosters on log1p(wait) and a CQR widening of the P10-P90 band."""

    def __init__(self, boosters: list[Booster] | None = None, qhat: float = 0.0) -> None:
        self.boosters = boosters or []
        self.qhat = qhat

    def fit(self, X: NDArray[np.float64], y: NDArray[np.float64], X_val: NDArray[np.float64],
            y_val: NDArray[np.float64]) -> WaitModel:  # fmt: skip
        params: dict[str, Any] = {
            "objective": "quantile", "n_estimators": 250, "learning_rate": 0.04,
            "num_leaves": 15, "min_child_samples": 30, "subsample": 0.8, "subsample_freq": 1,
            "random_state": 7, "verbose": -1,
        }  # fmt: skip
        self.boosters = [
            LGBMRegressor(alpha=a, **params).fit(X, np.log1p(y)).booster_ for a in QUANTILES
        ]
        lo, hi, _ = self._raw(X_val)
        scores = np.maximum(lo - np.log1p(y_val), np.log1p(y_val) - hi)
        n = len(scores)
        self.qhat = float(np.quantile(scores, min(1.0, np.ceil((n + 1) * LEVEL) / n)))
        return self

    def _raw(self, X: NDArray[np.float64]) -> tuple[NDArray[np.float64], ...]:
        lo, hi, mid = (np.asarray(b.predict(X)) for b in self.boosters)
        return lo, hi, mid

    def predict(
        self, X: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        lo, hi, mid = self._raw(X)
        lo, hi = lo - self.qhat, hi + self.qhat
        mid = np.clip(mid, lo, hi)
        return (
            np.clip(np.expm1(lo), 0, None),
            np.clip(np.expm1(mid), 0, None),
            np.clip(np.expm1(hi), 0, None),
        )

    def dump(self) -> dict[str, Any]:
        return {"boosters": [b.model_to_string() for b in self.boosters], "qhat": self.qhat,
                "features": FEATURES}  # fmt: skip

    @classmethod
    def load(cls, card: dict[str, Any]) -> WaitModel:
        return cls([Booster(model_str=s) for s in card["boosters"]], float(card["qhat"]))


def train(session: Session, locode: str = "BDCGP", save: bool = True) -> dict[str, Any]:
    t = table(session, locode)
    tr = np.flatnonzero(t.arrival < _h(SPLITS["train_until"]))
    va = np.flatnonzero(
        (t.arrival >= _h(SPLITS["train_until"])) & (t.arrival < _h(SPLITS["test_from"]))
    )
    te = np.flatnonzero(t.arrival >= _h(SPLITS["test_from"]))
    model = WaitModel().fit(t.X[tr], t.wait[tr], t.X[va], t.wait[va])
    base = baseline(t, te)
    ok = ~np.isnan(base[1])
    y = t.wait[te][ok]
    p = model.predict(t.X[te])
    m_bands = (p[0][ok], p[1][ok], p[2][ok])
    b_bands = (base[0][ok], base[1][ok], base[2][ok])
    report: dict[str, Any] = {
        "model": f"{NAME} {VERSION}", "features": FEATURES, "level": LEVEL,
        "split": {"train": len(tr), "validation": len(va), "test": int(ok.sum()),
                  "train_until": SPLITS["train_until"].date().isoformat(),
                  "test_from": SPLITS["test_from"].date().isoformat()},
        "test": {"model": score(y, m_bands), "baseline_30d": score(y, b_bands)},
        "label": "wait = CPA berthing - GFW arrival (container ships, matched visits)",
    }  # fmt: skip
    wins = report["test"]["model"]["pinball_h"] < report["test"]["baseline_30d"]["pinball_h"]
    report["active"] = bool(wins)
    if save:
        session.execute(
            update(ModelVersion).where(ModelVersion.name == NAME).values(is_active=False)
        )
        session.add(ModelVersion(
            capability="c4", name=NAME, version=VERSION, card=model.dump(), metrics=report,
            licence="code only; labels from GFW (CC BY-NC 4.0) and CPA public reports",
            is_active=bool(wins), source_id="c4", data_mode="replay", is_synthetic=False,
            available_at=datetime.now(UTC),
        ))  # fmt: skip
    return report


_cache: dict[str, Any] = {}


def active(session: Session) -> tuple[WaitModel, dict[str, Any]] | None:
    """The active berth-wait model (loaded once per process and model version)."""
    row = session.execute(
        select(ModelVersion.id, ModelVersion.card, ModelVersion.metrics)
        .where(ModelVersion.name == NAME, ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.registered_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    if _cache.get("id") != row[0]:
        _cache.update(id=row[0], model=WaitModel.load(row[1]), metrics=row[2])
    return _cache["model"], _cache["metrics"]


def predict_wait(
    session: Session, queue: int, at_berth: int, when: datetime
) -> tuple[float, float, float] | None:
    """P10/P50/P90 anchorage wait (h) for a container ship arriving at `when`, given the live
    queue and berth counts from CPA; None when no model is active."""
    got = active(session)
    if got is None:
        return None
    lo, mid, hi = got[0].predict(np.array([[queue, at_berth, *calendar(when)]]))
    return float(lo[0]), float(mid[0]), float(hi[0])
