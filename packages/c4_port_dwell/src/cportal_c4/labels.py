"""Port calls as arrays (the label factory's output, C4 §4) and the label-cleaning rules.

Times are float hours since the Unix epoch, so windows are `searchsorted` calls. Real calls are
GFW port visits (DS-AIS-02, total dwell = anchorage wait + berth time, D-04); a scenario adds its
own synthetic calls. GFW gives no wait/berth split for Chattogram (its stops carry no times).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import numpy as np
from cportal_core.models import Port, PortCall, Vessel, ZonePresenceDaily
from numpy.typing import NDArray
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cportal_c4.config import load_config

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def hours(ts: datetime | None) -> float:
    return float("nan") if ts is None else (ts - EPOCH).total_seconds() / 3600


def to_ts(h: float) -> datetime:
    return datetime.fromtimestamp(h * 3600, UTC)


@dataclass
class Calls:
    """One row per call, sorted by arrival."""

    ids: list[UUID]
    vessel_ids: list[UUID]
    mmsi: NDArray[np.int64]
    group: NDArray[np.str_]  # ship type group ("cargo", "tanker", …, "unknown")
    domestic: NDArray[np.bool_]  # Bangladesh flag: lighters and coasters
    arrival: NDArray[np.float64]
    departure: NDArray[np.float64]  # NaN while active
    confidence: NDArray[np.int64]
    flags: list[list[str]]
    synthetic: NDArray[np.bool_]
    names: list[str | None] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def dwell(self) -> NDArray[np.float64]:
        return self.departure - self.arrival

    def take(self, mask: NDArray[np.bool_]) -> Calls:
        idx = np.flatnonzero(mask)
        return Calls(
            ids=[self.ids[i] for i in idx],
            vessel_ids=[self.vessel_ids[i] for i in idx],
            mmsi=self.mmsi[idx],
            group=self.group[idx],
            domestic=self.domestic[idx],
            arrival=self.arrival[idx],
            departure=self.departure[idx],
            confidence=self.confidence[idx],
            flags=[self.flags[i] for i in idx],
            synthetic=self.synthetic[idx],
            names=[self.names[i] for i in idx] if self.names else [],
        )


def load_calls(
    session: Session, locode: str, scenario_id: UUID | None = None, real_only: bool = False
) -> Calls:
    """Real calls at a port, plus one scenario's synthetic calls when `scenario_id` is given."""
    port = session.scalar(select(Port).where(Port.locode == locode))
    if port is None:
        raise LookupError(f"unknown port {locode}")
    q = (
        select(PortCall, Vessel.mmsi, Vessel.ship_type_group, Vessel.flag_iso3, Vessel.name)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .where(PortCall.port_id == port.id, PortCall.arrival_ts.is_not(None))
    )
    if real_only or scenario_id is None:
        q = q.where(PortCall.is_synthetic.is_(False))
    else:
        q = q.where(or_(PortCall.is_synthetic.is_(False), PortCall.scenario_id == scenario_id))
    rows = session.execute(q.order_by(PortCall.arrival_ts, PortCall.id)).all()
    return Calls(
        ids=[c.id for c, *_ in rows],
        vessel_ids=[c.vessel_id for c, *_ in rows],
        mmsi=np.array([m or -1 for _, m, *_ in rows], dtype=np.int64),
        group=np.array([g or "unknown" for _, _, g, *_ in rows], dtype=np.str_),
        domestic=np.array([f == "BGD" for *_, f, _ in rows], dtype=np.bool_),
        arrival=np.array([hours(c.arrival_ts) for c, *_ in rows], dtype=np.float64),
        departure=np.array([hours(c.departure_ts) for c, *_ in rows], dtype=np.float64),
        confidence=np.array([c.confidence or 0 for c, *_ in rows], dtype=np.int64),
        flags=[list(c.quality_flags or []) for c, *_ in rows],
        synthetic=np.array([c.is_synthetic for c, *_ in rows], dtype=np.bool_),
        names=[n for *_, n in rows],
    )


def label_mask(calls: Calls) -> tuple[NDArray[np.bool_], dict[str, Any]]:
    """Calls usable as training labels, and how many each rule dropped (for the model card)."""
    cfg = load_config()["labels"]
    dwell = calls.dwell
    rules = {
        "active (censored)": np.isnan(dwell),
        "low confidence": calls.confidence < int(cfg["min_confidence"]),
        "started before the window": np.array(["window_overlap" in f for f in calls.flags]),
        "too short": dwell < float(cfg["min_dwell_h"]),
        "laid up (too long)": dwell > float(cfg["max_dwell_h"]),
    }
    keep = np.ones(len(calls), dtype=np.bool_)
    dropped: Counter[str] = Counter()
    for name, bad in rules.items():
        bad = bad & keep
        dropped[name] = int(bad.sum())
        keep &= ~bad
    return keep, {"total": len(calls), "kept": int(keep.sum()), "dropped": dict(dropped)}


def load_presence(
    session: Session, area: str, scenario_id: UUID | None = None
) -> dict[date, float]:
    """Vessels in an anchorage zone per day (GFW 4Wings, ≥ 1 h present), real or one scenario's."""
    q = (
        select(ZonePresenceDaily.date, func.count(func.distinct(ZonePresenceDaily.vessel_id)))
        .where(ZonePresenceDaily.area_name == area, ZonePresenceDaily.hours >= 1)
        .group_by(ZonePresenceDaily.date)
    )
    q = q.where(
        ZonePresenceDaily.is_synthetic.is_(False)
        if scenario_id is None
        else ZonePresenceDaily.scenario_id == scenario_id
    )
    return {d: float(n) for d, n in session.execute(q).all()}
