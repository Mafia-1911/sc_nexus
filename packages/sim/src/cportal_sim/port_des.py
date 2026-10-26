"""Chattogram port DES v0 (SimPy, 02 §9 "we build"): queues for real CPA berths, tidal windows
for deep-draught moves, lighterage at the anchorage, and closures that stop all work.

It replaces the AIS twin's independent visit planner: waits now emerge from berth contention,
tides and closures. Its visits feed (a) ground-truth port calls (`method=sim`, never shown as
real), and (b) the source twins in `twins.py`, which render GFW, PortWatch and aisstream wire
formats from them. Priors: config/priors/port_des.yaml (extends the AIS twin priors).
"""

from __future__ import annotations

import bisect
import math
import random
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import simpy
import yaml
from cportal_connectors.ais_synthetic import (
    AT_ANCHOR,
    MOORED,
    UNDERWAY,
    Leg,
    Visit,
    _jitter,
    _move,
    _vessel,
    _weighted,
)
from cportal_connectors.ais_synthetic import Vessel as TwinVessel
from cportal_core.paths import config_dir

GENERATOR = "cportal-sim/port_des/0.1.0"
OCEAN_TYPES = ("container", "tanker", "dry_bulk", "general_cargo", "roro")
# Vessel index = stream offset + arrival number, so each vessel's identity and random draws
# depend only on (seed, type, n), not on event order: runs with and without a closure share
# their random numbers (common random numbers) and differ only by the closure.
STREAM = {"container": 1, "tanker": 2, "dry_bulk": 3, "general_cargo": 4, "roro": 5, "lighter": 6}
Closure = tuple[datetime, datetime]


def load_priors(name: str = "port_des.yaml") -> dict[str, Any]:
    """The DES priors merged over the file they extend (top-level keys)."""
    path = config_dir() / "priors" / name
    data: dict[str, Any] = yaml.safe_load(path.read_text("utf-8"))
    if parent := data.pop("extends", None):
        base = load_priors(parent)
        base.update(data)
        data = base
    if "lighters" in data:
        data.setdefault("dimensions", {})["lighter"] = data["lighters"]["dimensions"]
    return data


@dataclass
class DesVisit:
    index: int
    vessel: TwinVessel
    kind: str  # an ocean type, or "lighter"
    mode: str  # berth | lighterage | lighter
    anchorage: dict[str, Any]
    arrive: datetime  # at the outer anchorage
    leave_anchorage: datetime
    depart: datetime  # leaves the port area
    berth_code: str | None = None
    berth_pool: str | None = None
    berth_start: datetime | None = None
    berth_end: datetime | None = None
    spot: tuple[float, float] = (0.0, 0.0)

    @property
    def waiting_h(self) -> float:
        end = self.berth_start or self.leave_anchorage
        return (end - self.arrive).total_seconds() / 3600

    @property
    def berth_h(self) -> float | None:
        if self.berth_start is None or self.berth_end is None:
            return None
        return (self.berth_end - self.berth_start).total_seconds() / 3600

    @property
    def dwell_h(self) -> float:
        """D-04: anchorage wait + berth time; the whole stay for anchorage-only visits."""
        if self.berth_end is not None:
            return (self.berth_end - self.arrive).total_seconds() / 3600
        return (self.leave_anchorage - self.arrive).total_seconds() / 3600


@dataclass
class DesResult:
    start: datetime
    end: datetime
    seed: int
    closures: list[Closure]
    priors: dict[str, Any]
    visits: list[DesVisit] = field(default_factory=list)

    def in_window(self) -> list[DesVisit]:
        return [v for v in self.visits if v.depart > self.start and v.arrive < self.end]


class PortDES:
    def __init__(
        self,
        priors: dict[str, Any],
        seed: int,
        start: datetime,
        end: datetime,
        closures: list[Closure] | None = None,
    ) -> None:
        self.priors = priors
        self.seed = seed
        self.start, self.end = start, end
        self.t0 = start - timedelta(days=int(priors.get("burn_in_days", 30)))
        self.closures = sorted(closures or [])
        self.env = simpy.Environment()
        self.pools: dict[str, simpy.Store] = {}
        for pool, codes in priors["berths"].items():
            store = simpy.Store(self.env)
            store.items.extend(codes)
            self.pools[pool] = store
        self.visits: list[DesVisit] = []
        self.channel = {
            "in": simpy.Resource(self.env, capacity=1),
            "out": simpy.Resource(self.env, capacity=1),
        }
        self.slot_h = float(priors.get("channel_slot_h", 0.0))
        self.evac = tuple(priors.get("evacuation_return_h", (0, 0)))
        tide = priors["tide"]
        anchor = datetime.fromisoformat(tide["anchor_high_water_local"]).astimezone(UTC)
        self.tide_period = float(tide["period_h"])
        self.tide_anchor = self.h(anchor)
        self.tide_window = float(tide["window_h"])
        self.deep = float(tide["deep_draught_m"])
        self._closure_h = [(self.h(a), self.h(b)) for a, b in self.closures]
        self._closure_starts = [a for a, _ in self._closure_h]

    # --- time helpers ------------------------------------------------------------------------

    def h(self, ts: datetime) -> float:
        return (ts - self.t0).total_seconds() / 3600

    def at(self, hours: float) -> datetime:
        return self.t0 + timedelta(hours=hours)

    @staticmethod
    def lognormal(spec: dict[str, float], rng: random.Random) -> float:
        return spec["median"] * math.exp(rng.gauss(0.0, spec["sigma"]))

    def closure_at(self, t: float) -> tuple[float, float] | None:
        for a, b in self._closure_h:
            if a <= t < b:
                return a, b
        return None

    def next_closure_start(self, t: float) -> float:
        i = bisect.bisect_right(self._closure_starts, t)
        return self._closure_starts[i] if i < len(self._closure_starts) else math.inf

    def tide_open(self, t: float) -> float:
        """Earliest time ≥ t inside a high-water window."""
        phase = (t - self.tide_anchor) % self.tide_period
        distance = min(phase, self.tide_period - phase)
        if distance <= self.tide_window:
            return t
        return t + (self.tide_period - phase) - self.tide_window

    def movable(self, t: float, deep: bool) -> float:
        """Earliest time ≥ t when a vessel may move: no closure, and a tide window if deep."""
        for _ in range(50):
            closure = self.closure_at(t)
            if closure:
                t = closure[1]
                continue
            nxt = self.tide_open(t) if deep else t
            if self.closure_at(nxt) is None:
                return nxt
            t = nxt
        return t

    def move(
        self, direction: str, deep: bool, not_before: float = 0.0
    ) -> Generator[simpy.Event, Any, None]:
        """Wait until moving is allowed (no closure, tide if deep), then take a channel slot."""
        while True:
            t = self.movable(max(self.env.now, not_before), deep)
            yield self.env.timeout(t - self.env.now)
            with self.channel[direction].request() as slot:
                yield slot
                if self.closure_at(self.env.now) is None and (
                    not deep or self.tide_open(self.env.now) == self.env.now
                ):
                    yield self.env.timeout(self.slot_h)
                    return

    def evacuation_end(self, since: float, until: float, return_h: float) -> float:
        """If a closure fell while the vessel waited at the anchorage, when it is back."""
        back = 0.0
        for a, b in self._closure_h:
            if since < b and a < until:
                back = max(back, b + return_h)
        return back

    def work(self, hours: float, return_h: float = 0.0) -> Generator[simpy.Event, Any, None]:
        """Spend `hours` of working time; the clock stops during closures. Vessels working at
        the anchorage (`return_h` > 0) were sent to sea and need `return_h` to come back."""
        remaining = hours
        while remaining > 1e-9:
            closure = self.closure_at(self.env.now)
            if closure:
                yield self.env.timeout(closure[1] - self.env.now + return_h)
                continue
            step = min(remaining, self.next_closure_start(self.env.now) - self.env.now)
            yield self.env.timeout(step)
            remaining -= step

    # --- processes -----------------------------------------------------------------------------

    def _new_vessel(
        self, kind: str, n: int
    ) -> tuple[int, TwinVessel, dict[str, Any], tuple[float, float], random.Random]:
        index = STREAM[kind] * 100_000 + n
        rng = random.Random(f"{self.seed}:vessel:{index}")
        vessel = _vessel(index, kind, self.priors, rng)
        cell = _weighted(self.priors["anchorage_cells"], rng)
        spot = _jitter((cell["lat"], cell["lon"]), 400, rng)
        return index, vessel, cell, spot, rng

    def arrivals(self, kind: str, per_day: float) -> Generator[simpy.Event, Any, None]:
        rng = random.Random(f"{self.seed}:arrivals:{kind}")
        end_h = self.h(self.end)
        n = 0
        while True:
            yield self.env.timeout(rng.expovariate(per_day / 24.0))
            if self.env.now >= end_h:
                return
            n += 1
            process = self.lighter(n) if kind == "lighter" else self.ocean(kind, n)
            self.env.process(process)

    def ocean(self, kind: str, n: int) -> Generator[simpy.Event, Any, None]:
        spec = self.priors["handling"][kind]
        index, vessel, cell, spot, rng = self._new_vessel(kind, n)
        arrive = self.env.now
        deep = vessel.draught > self.deep
        transit = float(self.priors.get("river_transit_h", 3.0))
        # Draw everything up front so a closure cannot change which draws a vessel gets.
        lighterage = rng.random() < float(spec.get("lighterage", 0.0))
        pre_berth = self.lognormal(spec["pre_berth"], rng)
        alongside = self.lognormal(spec["berth"], rng)
        lighter_work = self.lognormal(spec["lighter_work"], rng) if "lighter_work" in spec else 0.0
        pools = list(spec["pools"].items())
        pool = rng.choices([p for p, _ in pools], [w for _, w in pools])[0]
        return_h = rng.uniform(*self.evac)
        if lighterage:
            yield from self.work(lighter_work, return_h)
            leave = self.env.now
            self.visits.append(
                DesVisit(index, vessel, kind, "lighterage", cell, self.at(arrive), self.at(leave),
                         self.at(leave + 1.0), spot=spot)
            )  # fmt: skip
            return
        yield self.env.timeout(pre_berth)
        code = yield self.pools[pool].get()
        back = self.evacuation_end(arrive, self.movable(self.env.now, deep), return_h)
        yield from self.move("in", deep, not_before=back)
        leave = self.env.now
        yield self.env.timeout(transit)
        berth_start = self.env.now
        yield from self.work(alongside)
        yield from self.move("out", deep)
        berth_end = self.env.now
        yield self.pools[pool].put(code)
        self.visits.append(
            DesVisit(index, vessel, kind, "berth", cell, self.at(arrive), self.at(leave),
                     self.at(berth_end + transit), berth_code=code, berth_pool=pool,
                     berth_start=self.at(berth_start), berth_end=self.at(berth_end), spot=spot)
        )  # fmt: skip

    def lighter(self, n: int) -> Generator[simpy.Event, Any, None]:
        index, vessel, cell, spot, rng = self._new_vessel("lighter", n)
        arrive = self.env.now
        stay = self.lognormal(self.priors["lighters"]["stay"], rng)
        yield from self.work(stay, rng.uniform(*self.evac))
        leave = self.env.now
        self.visits.append(
            DesVisit(index, vessel, "lighter", "lighter", cell, self.at(arrive), self.at(leave),
                     self.at(leave + 0.5), spot=spot)
        )  # fmt: skip

    def run(self) -> DesResult:
        for kind in OCEAN_TYPES:
            self.env.process(self.arrivals(kind, float(self.priors["arrivals_per_day"][kind])))
        self.env.process(self.arrivals("lighter", float(self.priors["lighters"]["per_day"])))
        # Run past the window so visits that started inside it finish (no censoring in truth).
        self.env.run(until=self.h(self.end) + 24 * 60)
        self.visits.sort(key=lambda v: (v.arrive, v.index))
        return DesResult(self.start, self.end, self.seed, self.closures, self.priors, self.visits)


def simulate(
    start: datetime,
    end: datetime,
    seed: int = 42,
    closures: list[Closure] | None = None,
    priors: dict[str, Any] | None = None,
) -> DesResult:
    return PortDES(priors or load_priors(), seed, start, end, closures).run()


# --- snapshots ------------------------------------------------------------------------------------


def state_at(result: DesResult, ts: datetime) -> dict[str, Any]:
    """Queue, berth occupancy and 24 h flows at one instant, from the visit intervals."""
    waiting: dict[str, int] = {}
    working: dict[str, int] = {}
    occupied: dict[str, int] = {pool: 0 for pool in result.priors["berths"]}
    arrivals = departures = 0
    waits: list[float] = []
    day_ago = ts - timedelta(hours=24)
    for v in result.visits:
        if v.arrive <= ts < v.leave_anchorage:
            bucket = waiting if v.mode == "berth" else working
            bucket[v.kind] = bucket.get(v.kind, 0) + 1
        if v.berth_start and v.berth_end and v.berth_start <= ts < v.berth_end and v.berth_pool:
            occupied[v.berth_pool] += 1
        if day_ago < v.arrive <= ts and v.kind != "lighter":
            arrivals += 1
        if day_ago < v.depart <= ts and v.kind != "lighter":
            departures += 1
        if v.berth_start and day_ago < v.berth_start <= ts:
            waits.append(v.waiting_h)
    capacity = {pool: len(codes) for pool, codes in result.priors["berths"].items()}
    return {
        "queue_by_type": {"waiting_for_berth": waiting, "lighterage_or_lighter": working},
        "berth_occupancy": {p: {"occupied": occupied[p], "berths": capacity[p]} for p in capacity},
        "arrivals_24h": arrivals,
        "departures_24h": departures,
        "mean_wait_h_24h": round(sum(waits) / len(waits), 1) if waits else None,
    }


def present_on(result: DesResult, day_start: datetime) -> list[tuple[DesVisit, float]]:
    """Vessels with any time at the anchorage on a UTC day, with hours present that day."""
    day_end = day_start + timedelta(days=1)
    out = []
    for v in result.visits:
        a, b = max(v.arrive, day_start), min(v.leave_anchorage, day_end)
        if b > a:
            out.append((v, (b - a).total_seconds() / 3600))
    return out


# --- AIS twin geometry ----------------------------------------------------------------------------


def to_twin_visit(v: DesVisit, priors: dict[str, Any], seed: int) -> Visit:
    """Legs for the AIS twin's frame encoder, consistent with the DES times."""
    rng = random.Random(f"{seed}:legs:{v.index}")
    speeds = priors["speeds_kn"]
    entry = priors["sea_entry"]
    sea = _jitter((entry["lat"], entry["lon"]), entry["jitter_deg"] * 111_000, rng)
    river = [(w["lat"], w["lon"]) for w in priors["river_waypoints"]]
    approach = _move(v.arrive, [sea, v.spot], rng.uniform(*speeds["approach"]))
    shift = approach.end - approach.start
    legs = [Leg(v.arrive - shift, v.arrive, approach.path, UNDERWAY)]
    legs.append(Leg(v.arrive, v.leave_anchorage, [v.spot], AT_ANCHOR))
    berth = None
    if v.mode == "berth" and v.berth_start and v.berth_end:
        cells = priors["berth_cells"].get(v.kind) or priors["berth_cells"]["general_cargo"]
        berth = _weighted(cells, rng)
        quay = _jitter((berth["lat"], berth["lon"]), 150, rng)
        legs.append(Leg(v.leave_anchorage, v.berth_start, [v.spot, *river, quay], UNDERWAY))
        legs.append(Leg(v.berth_start, v.berth_end, [quay], MOORED))
        legs.append(
            _move(v.berth_end, [quay, *reversed(river), sea], rng.uniform(*speeds["departure"]))
        )
    else:
        legs.append(_move(v.leave_anchorage, [v.spot, sea], rng.uniform(*speeds["departure"])))
    visit = Visit(v.index, v.vessel, v.anchorage, berth, legs=legs)
    visit.truth = {"arrive_anchorage": v.arrive}
    return visit
