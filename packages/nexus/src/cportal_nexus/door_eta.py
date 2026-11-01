"""Door ETA (08 §1, NX-R01): Monte Carlo over a shipment's remaining legs.

Each sample walks the legs in order. A leg never leaves before its planned departure; lateness
carries forward. Moving time = planned duration × lognormal noise by mode (median = plan). At the
gateway (Chattogram) the stay deviates from plan by C4's vessel dwell (sampled from recent C4
port-call predictions, minus their median) plus the container dwell prior (minus its median).
A disruption at a location pauses the stay there: arriving during it waits until it ends, and a
stay that spans its start is extended by its whole length (sampled from the event's P50/P90).
Output: P10/P50/P90 door time, P(on time) against the order's due time, mean extra hours by driver.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

import numpy as np

Z90 = 1.2816  # standard normal 90th percentile
GATEWAY_VESSEL = "Chattogram vessel wait and berth (C4)"
GATEWAY_DWELL = "Chattogram container dwell (yard and customs)"
SCHEDULE = "schedules and connections"


@dataclass(frozen=True)
class Leg:
    seq: int
    mode: str
    from_locode: str | None
    to_locode: str | None
    planned_dep: datetime
    planned_arr: datetime
    actual_dep: datetime | None = None
    actual_arr: datetime | None = None


@dataclass(frozen=True)
class Hold:
    """A disruption that pauses shipments at a location while it lasts."""

    label: str
    locode: str
    start: datetime
    p50_h: float
    p90_h: float
    prob: float = 1.0  # confidence that it happens (per sample, Bernoulli)


@dataclass(frozen=True)
class Priors:
    leg_sigma: dict[str, float]  # lognormal σ of moving time by mode
    container_dwell_h: tuple[float, float]  # P50, P90 at the gateway (yard + customs)
    gateway: str = "BDCGP"
    samples: int = 1000


@dataclass
class DoorEta:
    planned: datetime
    p10: datetime
    p50: datetime
    p90: datetime
    on_time_prob: float | None
    drivers: list[tuple[str, float]] = field(default_factory=list)  # label, mean extra hours
    n: int = 0


def split_lognormal(
    p10: np.ndarray | float, p50: np.ndarray | float, p90: np.ndarray | float, z: np.ndarray
) -> np.ndarray:
    """Exact at P10/P50/P90: σ below the median from P10, above it from P90."""
    m = np.maximum(np.asarray(p50, dtype=float), 1e-3)
    lo = (np.log(m) - np.log(np.maximum(np.asarray(p10, dtype=float), 1e-3))) / Z90
    hi = (np.log(np.maximum(np.asarray(p90, dtype=float), 1e-3)) - np.log(m)) / Z90
    return np.asarray(m * np.exp(np.where(z < 0, z * lo, z * hi)))


def from_p50_p90(p50: float, p90: float, z: np.ndarray) -> np.ndarray:
    """Lognormal through P50 and P90 (symmetric in log space)."""
    p90 = max(p90, p50)
    return split_lognormal(p50 * p50 / p90, p50, p90, z)


def _h(td: timedelta) -> float:
    return td.total_seconds() / 3600.0


def simulate(
    legs: Sequence[Leg],
    now: datetime,
    due: datetime | None,
    priors: Priors,
    vessel_stay_q: Sequence[dict[str, float]],
    holds: Sequence[Hold] = (),
    seed: int = 0,
) -> DoorEta:
    order = sorted(legs, key=lambda x: x.seq)
    n = priors.samples
    rng = np.random.default_rng(seed)
    drivers: dict[str, np.ndarray] = {}

    def add(label: str, extra: np.ndarray) -> None:
        drivers[label] = drivers.get(label, np.zeros(n)) + extra

    def at(x: datetime) -> float:
        return _h(x - now)

    vq = np.array([[q.get("p10", q["p50"]), q["p50"], q.get("p90", q["p50"])]
                   for q in vessel_stay_q]) if vessel_stay_q else np.zeros((0, 3))  # fmt: skip
    vessel_ref = float(np.median(vq[:, 1])) if len(vq) else 0.0
    cd50, cd90 = priors.container_dwell_h
    t = np.zeros(n)  # hours after `now`
    prev: Leg | None = None
    for leg in order:
        if leg.actual_arr is not None:
            t = np.full(n, max(at(leg.actual_arr), 0.0))
            prev = leg
            continue
        if leg.actual_dep is not None:
            dep = np.zeros(n)
        else:
            slack = max(_h(leg.planned_dep - prev.planned_arr), 0.0) if prev else 0.0
            ready = t + slack
            place = leg.from_locode
            if place == priors.gateway and prev is not None:
                if len(vq):
                    i = rng.integers(0, len(vq), n)
                    stay = split_lognormal(vq[i, 0], vq[i, 1], vq[i, 2], rng.standard_normal(n))
                    ready = ready + (stay - vessel_ref)
                    add(GATEWAY_VESSEL, stay - vessel_ref)
                dwell = from_p50_p90(cd50, cd90, rng.standard_normal(n))
                ready = ready + (dwell - cd50)
                add(GATEWAY_DWELL, dwell - cd50)
            for h in holds:
                if place is None or h.locode != place:
                    continue
                s = at(h.start)
                # Own stream per event: with/without runs share every other draw (common
                # random numbers), so a scenario comparison shows only the event's effect.
                hz = np.random.default_rng([seed, zlib.crc32(f"{h.label}|{h.locode}".encode())])
                e = s + from_p50_p90(h.p50_h, h.p90_h, hz.standard_normal(n))
                on = hz.random(n) < h.prob
                extra = np.where(on & (ready > s) & (t < e), e - np.maximum(t, s), 0.0)
                ready = ready + extra
                add(h.label, extra)
            dep = np.maximum(np.maximum(ready, at(leg.planned_dep)), 0.0)
        noise = np.exp(priors.leg_sigma.get(leg.mode, 0.2) * rng.standard_normal(n))
        if leg.actual_dep is not None:
            # Under way: only the remaining time is uncertain; the late start carries over.
            late_start = _h(leg.actual_dep - leg.planned_dep)
            remaining = max(at(leg.planned_arr) + late_start, 0.0)
            arr = remaining * noise
            add(f"{leg.mode} legs", arr - remaining)
        else:
            plan_h = max(_h(leg.planned_arr - leg.planned_dep), 0.0)
            move = plan_h * noise
            arr = dep + move
            add(f"{leg.mode} legs", move - plan_h)
        t = arr
        prev = leg
    planned = order[-1].planned_arr
    explained = np.sum(list(drivers.values()), axis=0) if drivers else np.zeros(n)
    add(SCHEDULE, t - at(planned) - explained)
    q10, q50, q90 = np.quantile(t, [0.1, 0.5, 0.9])
    ranked = sorted(((k, float(np.mean(v))) for k, v in drivers.items()), key=lambda kv: -kv[1])
    return DoorEta(
        planned=planned,
        p10=now + timedelta(hours=float(q10)),
        p50=now + timedelta(hours=float(q50)),
        p90=now + timedelta(hours=float(q90)),
        on_time_prob=float(np.mean(t <= at(due))) if due is not None else None,
        drivers=[(k, round(v, 1)) for k, v in ranked if abs(v) >= 0.5],
        n=n,
    )


def due_time(due: date | None) -> datetime | None:
    """End of the due day in Dhaka (23:59, UTC+6) as UTC."""
    return None if due is None else datetime.combine(due, time(17, 59), UTC)


def as_hours(x: datetime, now: datetime) -> float:
    return round(_h(x - now), 2)
