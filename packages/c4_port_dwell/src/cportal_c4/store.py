"""Database side of C4: model versions and replay predictions (`prediction`, capability c4).

Three prediction kinds, all `data_mode = replay` on real GFW calls:
- `port_call`: dwell P10/P50/P90 at arrival, with drivers and the L0 baseline;
- `port_call_remaining`: remaining hours P10/P50/P90 at each noon snapshot while in port;
- `port_queue`: anchorage history (60 days) and the 14-day fan at each snapshot.
Ids are deterministic and every run replaces the port's rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np
from cportal_core.models import ModelVersion, Port, Prediction
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from cportal_c4 import MODEL_VERSION
from cportal_c4.labels import hours, to_ts
from cportal_c4.pipeline import Run, snapshots
from cportal_c4.survival import remaining

NS = uuid5(NAMESPACE_URL, "cportal/c4")
CHUNK = 2000
LICENCE = "code only; trained on GFW data (CC BY-NC 4.0, non-commercial)"
MODELS = {
    "dwell": ("c4-dwell-lgbm-cqr", "LightGBM P10/P50/P90 + MAPIE conformal (L1)"),
    "baseline": ("c4-dwell-median", "Median by type × flag × month (L0)"),
    "remaining": ("c4-remaining-rsf", "Random survival forest, conditional on time in port (L2)"),
    "queue": ("c4-queue-lgbm", "Direct LightGBM + conformal bands, 1–14 days (L3)"),
}


def _lineage(key: str) -> dict[str, Any]:
    return {
        "source_id": "c4",
        "source_record_id": key[:256],
        "data_mode": "replay",
        "is_synthetic": False,
        "generator_version": MODEL_VERSION,
    }


def register(session: Session, run: Run) -> dict[str, UUID]:
    r = run.report
    metrics = {
        "dwell": r["dwell"] | {"lag_ablation": r.get("lag_ablation")},
        "baseline": {k: v for k, v in r["dwell"].items() if k.startswith("L0")},
        "remaining": r["remaining"],
        "queue": r.get("queue", {}),
    }
    ids = {}
    for key, (name, title) in MODELS.items():
        mid = uuid5(NS, f"model:{name}:{run.locode}")
        session.merge(
            ModelVersion(
                id=mid,
                **_lineage(f"{run.locode}:{name}"),
                capability="c4",
                name=f"{name} ({run.locode})",
                version=MODEL_VERSION,
                artifact_uri=None,
                card={
                    "title": title,
                    "path": "docs/model-cards/c4-port-dwell.md",
                    "split": r["split"],
                    "trained_at": r["trained_at"],
                },
                metrics=metrics[key],
                licence=LICENCE,
                is_active=key != "baseline",
            )
        )
        ids[key] = mid
    return ids


def save(session: Session, run: Run, ids: dict[str, UUID]) -> dict[str, int]:
    """Replace the port's replay predictions."""
    session.execute(
        delete(Prediction).where(
            Prediction.capability == "c4", Prediction.source_record_id.like(f"{run.locode}:%")
        )
    )
    calls, X = run.calls, run.X
    times = snapshots(run)
    t = np.array([hours(s) for s in times])
    dep = np.where(np.isnan(calls.departure), np.inf, calls.departure)
    present = (calls.arrival[:, None] < t[None, :]) & (dep[:, None] > t[None, :])
    present &= calls.arrival[:, None] > t[None, :] - 24 * 60  # laid-up vessels are not queueing
    idx = np.flatnonzero(present.any(axis=1))
    bands = run.dwell.predict(X[idx])
    base = run.baseline.predict(calls.take(np.isin(np.arange(len(calls)), idx)), X[idx])
    drivers = run.dwell.drivers(X[idx])
    curves = run.remaining.curves(X[idx])
    rows: list[dict[str, Any]] = []
    for k, i in enumerate(idx):
        key = f"{run.locode}:call:{calls.ids[i]}"
        rows.append(
            _row(key, ids["dwell"], "port_call", calls.ids[i], to_ts(calls.arrival[i]), None,
                 [bands[0][k], bands[1][k], bands[2][k]],
                 {"drivers": drivers[k], "baseline": [round(float(b[k]), 1) for b in base]})
        )  # fmt: skip
        for j in np.flatnonzero(present[i]):
            elapsed = float(t[j] - calls.arrival[i])
            lo, mid, hi = remaining(run.remaining.times, curves[k], elapsed)
            km = run.remaining.baseline(np.array([elapsed]))[0]
            rows.append(
                _row(f"{key}:{times[j].isoformat()}", ids["remaining"], "port_call_remaining",
                     calls.ids[i], times[j], mid, [lo, mid, hi],
                     {"elapsed_h": round(elapsed, 1), "baseline": [round(v, 1) for v in km]})
            )  # fmt: skip
    if run.queue is not None and run.series is not None:
        port_id = session.scalar(select(Port.id).where(Port.locode == run.locode))
        assert port_id is not None
        days, values = run.series
        for s in times:
            last = days.index(s.date() - timedelta(days=1))
            fan = run.queue.predict(days, values, last)
            hist = [[days[d].isoformat(), float(values[d])] for d in range(last - 59, last + 1)]
            future = [
                [(days[last] + timedelta(days=h + 1)).isoformat(), *map(float, fan[h])]
                for h in range(len(fan))
            ]
            rows.append(
                _row(f"{run.locode}:queue:{s.isoformat()}", ids["queue"], "port_queue", port_id,
                     s, float(fan[6][1]), [float(v) for v in fan[6]],
                     {"history": hist, "forecast": future}, horizon_h=168.0)
            )  # fmt: skip
    for start in range(0, len(rows), CHUNK):
        session.execute(insert(Prediction), rows[start : start + CHUNK])
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["target_type"]] = kinds.get(r["target_type"], 0) + 1
    return kinds


def _row(
    key: str,
    model_id: UUID,
    target_type: str,
    target_id: UUID,
    as_of: datetime,
    value: float | None,
    q: list[float],
    extra: dict[str, Any],
    horizon_h: float | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid5(NS, key),
        **_lineage(key),
        "available_at": as_of,
        "capability": "c4",
        "target_type": target_type,
        "target_id": target_id,
        "as_of": as_of,
        "horizon_h": horizon_h,
        "value": None if value is None else round(float(value), 2),
        "quantiles": {k: round(float(v), 2) for k, v in zip(("p10", "p50", "p90"), q, strict=True)},
        "dist_params": extra if target_type == "port_queue" else {},
        "model_version_id": model_id,
        "explanation": extra if target_type != "port_queue" else {},
        "features_hash": None,
    }


def refresh(session: Session, run: Run) -> dict[str, Any]:
    ids = register(session, run)
    session.flush()
    counts = save(session, run, ids)
    return {"predictions": counts, "at": datetime.now(UTC).isoformat(timespec="seconds")}
