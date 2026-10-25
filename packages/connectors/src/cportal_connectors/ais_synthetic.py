"""DS-AIS-01 synthetic twin: aisstream-format frames for Chattogram plus ground-truth port calls.

aisstream has no receiver coverage around Bangladesh (probe of 2026-10-26: 0 messages in 10 min
over the Bay of Bengal approach while the same key streamed 44 msg/s worldwide). This twin
emits frames in exactly the shape aisstream sends (MetaData / MessageType / Message, Go-style
`time_utc`, padded `ShipName`, AIS sentinels), wrapped in the collector's envelope plus
`is_synthetic` and `scenario_id`, so every consumer of the collector's files reads both.

Vessels are fictional: MMSIs use MID 999, which no administration holds, and names start with
"SYN". Arrival rates and port times are calibrated to PortWatch and GFW (config/priors/
ds_ais_01_synthetic.yaml). Berth capacity, tides and evacuations are not modelled here: the
SimPy port DES replaces `plan_visits` in M1 and keeps this module's encoders.

    uv run ais-synth --scenario baseline --hours 168 --seed 42
    uv run ais-synth --scenario cyclone --closure 2026-10-22T06:00,42
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import random
import statistics
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml
from cportal_core.paths import config_dir, repo_root

GENERATOR = "ds_ais_01_synthetic/0.1.0"
PRIORS = "priors/ds_ais_01_synthetic.yaml"
MID = 999
BURN_IN = timedelta(days=21)
KM_PER_DEG_LAT = 110.574
KM_PER_NM = 1.852
ADJECTIVES = [
    "AMBER",
    "BRISK",
    "CEDAR",
    "CORAL",
    "DAWN",
    "EMBER",
    "FERN",
    "GALE",
    "HAZEL",
    "IRIS",
    "JADE",
    "KESTREL",
    "LUMEN",
    "MAPLE",
    "NIMBUS",
    "ONYX",
    "PEARL",
    "QUILL",
    "RUSSET",
    "SABLE",
    "TEAL",
    "UMBER",
    "VESPER",
    "WILLOW",
]
NOUNS = [
    "TIDE",
    "HARBOR",
    "MERIDIAN",
    "CURRENT",
    "ANCHOR",
    "COMPASS",
    "HORIZON",
    "LANTERN",
    "SOUND",
    "REACH",
    "SHOAL",
    "BEACON",
    "CAPE",
    "DELTA",
    "ESTUARY",
    "FATHOM",
]
# AIS navigational status codes (ITU-R M.1371).
UNDERWAY, AT_ANCHOR, MOORED = 0, 1, 5
LatLon = tuple[float, float]


@dataclass(frozen=True)
class Vessel:
    mmsi: int
    name: str
    callsign: str
    kind: str
    loa: int
    beam: int
    draught: float
    ais_type: int
    destination: str


@dataclass
class Leg:
    """Constant-speed motion along a polyline; one point means stationary."""

    start: datetime
    end: datetime
    path: list[LatLon]
    status: int


@dataclass
class Visit:
    index: int
    vessel: Vessel
    anchorage: dict[str, Any]
    berth: dict[str, Any] | None
    legs: list[Leg] = field(default_factory=list)
    truth: dict[str, Any] = field(default_factory=dict)

    @property
    def start(self) -> datetime:
        return self.legs[0].start

    @property
    def end(self) -> datetime:
        return self.legs[-1].end


def go_time(t: datetime, nanos: int) -> str:
    """aisstream's MetaData.time_utc: Go's time.String() with nanoseconds."""
    return f"{t:%Y-%m-%d %H:%M:%S}.{t.microsecond:06d}{nanos:03d} +0000 UTC"


def _meta(v: Vessel, t: datetime, lat: float, lon: float, nanos: int) -> dict[str, Any]:
    return {
        "MMSI": v.mmsi,
        "MMSI_String": v.mmsi,
        "ShipName": v.name.ljust(20),
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "time_utc": go_time(t, nanos),
    }


def encode_position(
    v: Vessel,
    t: datetime,
    lat: float,
    lon: float,
    sog: float,
    cog: float,
    status: int,
    rng: random.Random,
) -> dict[str, Any]:
    moving = sog >= 0.5
    return {
        "MetaData": _meta(v, t, lat, lon, rng.randrange(1000)),
        "MessageType": "PositionReport",
        "Message": {
            "PositionReport": {
                "MessageID": rng.choice((1, 3)),
                "RepeatIndicator": 0,
                "UserID": v.mmsi,
                "Valid": True,
                "NavigationalStatus": status,
                "RateOfTurn": 0 if moving else -128,  # -128: no turn information
                "Sog": round(sog, 1),
                "PositionAccuracy": rng.random() < 0.7,
                "Longitude": lon,
                "Latitude": lat,
                "Cog": round(cog, 1) if moving else 360,  # 360: not available
                "TrueHeading": round(cog) % 360
                if moving
                else rng.choice((511, rng.randrange(360))),
                "Timestamp": t.second,
                "SpecialManoeuvreIndicator": 0,
                "Spare": 0,
                "Raim": rng.random() < 0.5,
                "CommunicationState": rng.randrange(2**19),
            }
        },
    }


def encode_static(
    v: Vessel, t: datetime, lat: float, lon: float, eta: datetime, rng: random.Random
) -> dict[str, Any]:
    bow = round(v.loa * 0.85)
    port_side = v.beam // 2
    return {
        "MetaData": _meta(v, t, lat, lon, rng.randrange(1000)),
        "MessageType": "ShipStaticData",
        "Message": {
            "ShipStaticData": {
                "AisVersion": 1,
                "CallSign": v.callsign,
                "Destination": v.destination,
                "Dimension": {"A": bow, "B": v.loa - bow, "C": port_side, "D": v.beam - port_side},
                "Dte": False,
                "Eta": {"Day": eta.day, "Hour": eta.hour, "Minute": eta.minute, "Month": eta.month},
                "FixType": 1,
                "ImoNumber": 0,
                "MaximumStaticDraught": v.draught,
                "MessageID": 5,
                "Name": v.name,
                "RepeatIndicator": 0,
                "Spare": False,
                "Type": v.ais_type,
                "UserID": v.mmsi,
                "Valid": True,
            }
        },
    }


def distance_km(a: LatLon, b: LatLon) -> float:
    dy = (b[0] - a[0]) * KM_PER_DEG_LAT
    dx = (b[1] - a[1]) * KM_PER_DEG_LAT * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.degrees(math.atan2(dx, dy)) % 360


def along(path: list[LatLon], frac: float) -> tuple[LatLon, float]:
    """Point at fraction `frac` of the polyline's length, and the heading there."""
    if len(path) == 1:
        return path[0], 0.0
    lengths = [distance_km(a, b) for a, b in pairwise(path)]
    target = max(0.0, min(1.0, frac)) * sum(lengths)
    for (a, b), seg in zip(pairwise(path), lengths, strict=True):
        if target <= seg or seg == 0:
            f = target / seg if seg else 0.0
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), bearing_deg(a, b)
        target -= seg
    return path[-1], bearing_deg(path[-2], path[-1])


def _jitter(p: LatLon, metres: float, rng: random.Random) -> LatLon:
    r = metres * math.sqrt(rng.random()) / 1000
    theta = rng.random() * 2 * math.pi
    dlat = r * math.cos(theta) / KM_PER_DEG_LAT
    dlon = r * math.sin(theta) / (KM_PER_DEG_LAT * math.cos(math.radians(p[0])))
    return p[0] + dlat, p[1] + dlon


def _lognormal_h(spec: dict[str, float], rng: random.Random) -> timedelta:
    return timedelta(hours=rng.lognormvariate(math.log(spec["median"]), spec["sigma"]))


def _weighted(cells: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    return rng.choices(cells, weights=[c["weight"] for c in cells])[0]


def _after_closures(
    t: datetime, closures: list[tuple[datetime, datetime]], rng: random.Random
) -> datetime:
    """River transits wait for the end of any closure, then queue for up to six hours."""
    for start, end in closures:
        if start <= t < end:
            return end + timedelta(hours=rng.uniform(0, 6))
    return t


def _move(start: datetime, path: list[LatLon], knots: float, status: int = UNDERWAY) -> Leg:
    hours = sum(distance_km(a, b) for a, b in pairwise(path)) / (knots * KM_PER_NM)
    return Leg(start, start + timedelta(hours=hours), path, status)


def plan_visits(
    priors: dict[str, Any],
    window_end: datetime,
    seed: int,
    closures: list[tuple[datetime, datetime]],
) -> list[Visit]:
    """Poisson arrivals per vessel type from BURN_IN before the window; exogenous durations."""
    rng = random.Random(f"{seed}:plan")
    sim_start = window_end - BURN_IN - timedelta(days=7)
    arrivals: list[tuple[datetime, str]] = []
    for kind, per_day in priors["arrivals_per_day"].items():
        t = sim_start
        while True:
            t += timedelta(days=rng.expovariate(per_day))
            if t >= window_end:
                break
            arrivals.append((t, kind))
    arrivals.sort()
    speeds = priors["speeds_kn"]
    river = [(w["lat"], w["lon"]) for w in priors["river_waypoints"]]
    visits = []
    for index, (arrive, kind) in enumerate(arrivals):
        vessel = _vessel(index, kind, priors, rng)
        cell = _weighted(priors["anchorage_cells"], rng)
        spot = _jitter((cell["lat"], cell["lon"]), 400, rng)
        entry = priors["sea_entry"]
        sea = _jitter((entry["lat"], entry["lon"]), entry["jitter_deg"] * 111_000, rng)
        spec = priors["durations_h"][kind]
        approach = _move(arrive, [sea, spot], rng.uniform(*speeds["approach"]))
        shift = approach.end - approach.start  # approach ends exactly at the arrival time
        approach = Leg(arrive - shift, arrive, approach.path, UNDERWAY)
        lighterage = rng.random() < float(spec.get("lighterage_share", 0.0))
        berth = None if lighterage else _weighted(priors["berth_cells"][kind], rng)
        visit = Visit(index, vessel, cell, berth, legs=[approach])
        wait_end = arrive + _lognormal_h(spec["anchorage"], rng)
        truth: dict[str, Any] = {"arrive_anchorage": arrive, "lighterage": lighterage}
        if berth is None:
            visit.legs.append(Leg(arrive, wait_end, [spot], AT_ANCHOR))
            out = _move(wait_end, [spot, sea], rng.uniform(*speeds["departure"]))
            visit.legs.append(out)
            truth |= {"berth_start": None, "berth_end": None, "leave_anchorage": wait_end}
        else:
            quay = _jitter((berth["lat"], berth["lon"]), 150, rng)
            transit_start = _after_closures(wait_end, closures, rng)
            visit.legs.append(Leg(arrive, transit_start, [spot], AT_ANCHOR))
            inbound = _move(transit_start, [spot, *river, quay], rng.uniform(*speeds["river"]))
            visit.legs.append(inbound)
            alongside_end = inbound.end + _lognormal_h(spec["berth"], rng)
            outbound_start = _after_closures(alongside_end, closures, rng)
            visit.legs.append(Leg(inbound.end, outbound_start, [quay], MOORED))
            outbound = _move(
                outbound_start, [quay, *reversed(river), sea], rng.uniform(*speeds["departure"])
            )
            visit.legs.append(outbound)
            truth |= {
                "berth_start": inbound.end,
                "berth_end": outbound_start,
                "leave_anchorage": transit_start,
            }
        truth["depart_area"] = visit.end
        visit.truth = truth
        visits.append(visit)
    return visits


def _vessel(index: int, kind: str, priors: dict[str, Any], rng: random.Random) -> Vessel:
    dims = priors["dimensions"][kind]
    adjective = ADJECTIVES[index % len(ADJECTIVES)]
    noun = NOUNS[(index // len(ADJECTIVES)) % len(NOUNS)]
    name = f"SYN {adjective} {noun}"
    if index >= len(ADJECTIVES) * len(NOUNS):
        name += f" {index // (len(ADJECTIVES) * len(NOUNS)) + 1}"
    return Vessel(
        mmsi=MID * 1_000_000 + index + 1,
        name=name,
        callsign=f"SYN{index % 10000:04d}",
        kind=kind,
        loa=rng.randint(*dims["loa"]),
        beam=rng.randint(*dims["beam"]),
        draught=round(rng.uniform(*dims["draught"]), 1),
        ais_type=dims["ais_type"],
        destination=rng.choice(priors["destinations"]),
    )


def _state(visit: Visit, t: datetime) -> tuple[LatLon, float, float, int] | None:
    starts = [leg.start for leg in visit.legs]
    i = bisect.bisect_right(starts, t) - 1
    if i < 0 or t >= visit.end:
        return None
    leg = visit.legs[i]
    span = (leg.end - leg.start).total_seconds()
    frac = (t - leg.start).total_seconds() / span if span > 0 else 0.0
    point, heading = along(leg.path, frac)
    if len(leg.path) == 1:
        return point, 0.0, heading, leg.status
    km = sum(distance_km(a, b) for a, b in pairwise(leg.path))
    knots = km / KM_PER_NM / (span / 3600) if span else 0.0
    return point, knots, heading, leg.status


def frames_for_hour(
    visits: list[Visit], hour: datetime, priors: dict[str, Any], seed: int, scenario: str
) -> list[dict[str, Any]]:
    report_s = priors["reporting_s"]
    receiver = priors["receiver"]
    end = hour + timedelta(hours=1)
    outage_rng = random.Random(f"{seed}:outage:{hour.isoformat()}")
    outage: tuple[datetime, datetime] | None = None
    if outage_rng.random() < receiver["outage_per_hour"]:
        o_start = hour + timedelta(minutes=outage_rng.uniform(0, 30))
        outage = (o_start, o_start + timedelta(minutes=30))
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for visit in visits:
        if visit.end <= hour or visit.start >= end:
            continue
        rng = random.Random(f"{seed}:{visit.index}:{hour.isoformat()}")
        v = visit.vessel
        for t in _ticks(hour, end, visit, report_s, rng):
            state = _state(visit, t)
            if state is None or rng.random() < receiver["drop_probability"]:
                continue
            (lat, lon), knots, heading, status = state
            lat, lon = _jitter((lat, lon), receiver["position_noise_m"], rng)
            if status in (AT_ANCHOR, MOORED) and rng.random() < 0.15:
                status = UNDERWAY  # real vessels often leave the status at "under way"
            rows.append(
                _envelope(
                    t, encode_position(v, t, lat, lon, knots, heading, status, rng), rng, scenario
                )
            )
        # Static data on its own 6-minute schedule, phase-shifted per vessel.
        period = report_s["static"]
        phase = (visit.index * 37) % period
        first = hour + timedelta(seconds=(phase - hour.timestamp()) % period)
        t = first
        while t < end:
            state = _state(visit, t)
            if state is not None and rng.random() >= receiver["drop_probability"]:
                (lat, lon), *_ = state
                eta = visit.truth["arrive_anchorage"]
                rows.append(_envelope(t, encode_static(v, t, lat, lon, eta, rng), rng, scenario))
            t += timedelta(seconds=period)
    if outage:
        rows = [r for r in rows if not outage[0] <= r[0] < outage[1]]
    rows.sort(key=lambda r: r[0])
    return [row for _, row in rows]


def _ticks(
    hour: datetime, end: datetime, visit: Visit, report_s: dict[str, int], rng: random.Random
) -> Iterator[datetime]:
    t = hour + timedelta(seconds=rng.uniform(0, report_s["underway"]))
    while t < end:
        state = _state(visit, t)
        stationary = state is not None and state[1] < 0.5
        yield t
        step = report_s["stationary"] if stationary else report_s["underway"]
        t += timedelta(seconds=step * rng.uniform(0.9, 1.1))


def _envelope(
    t: datetime, frame: dict[str, Any], rng: random.Random, scenario: str
) -> tuple[datetime, dict[str, Any]]:
    """Same envelope as the live collector, plus the synthetic labels (AGENTS.md rule 3)."""
    received = t + timedelta(milliseconds=rng.uniform(100, 1500))
    return received, {
        "received_at": received.isoformat(),
        "frame": json.dumps(frame),
        "is_synthetic": True,
        "scenario_id": scenario,
        "generator": GENERATOR,
    }


def ground_truth(visit: Visit, scenario: str) -> dict[str, Any]:
    t = visit.truth
    berth_h = (
        (t["berth_end"] - t["berth_start"]).total_seconds() / 3600 if t["berth_start"] else 0.0
    )
    wait_h = (t["leave_anchorage"] - t["arrive_anchorage"]).total_seconds() / 3600
    return {
        "mmsi": visit.vessel.mmsi,
        "name": visit.vessel.name,
        "vessel_type": visit.vessel.kind,
        "anchorage_cell": visit.anchorage["id"],
        "berth_cell": (visit.berth or {}).get("id"),
        "lighterage": t["lighterage"],
        "approach_start": visit.start.isoformat(),
        "arrive_anchorage": t["arrive_anchorage"].isoformat(),
        "leave_anchorage": t["leave_anchorage"].isoformat(),
        "berth_start": t["berth_start"].isoformat() if t["berth_start"] else None,
        "berth_end": t["berth_end"].isoformat() if t["berth_end"] else None,
        "depart_area": t["depart_area"].isoformat(),
        "anchorage_wait_h": round(wait_h, 2),
        "berth_h": round(berth_h, 2),
        "vessel_dwell_h": round(wait_h + berth_h, 2),  # D-04: anchorage wait + berth time
        "is_synthetic": True,
        "scenario_id": scenario,
    }


def generate(
    scenario: str,
    start: datetime,
    hours: int,
    seed: int,
    closures: list[tuple[datetime, datetime]],
    root: Path,
) -> dict[str, Any]:
    priors_path = config_dir() / PRIORS
    priors = yaml.safe_load(priors_path.read_text(encoding="utf-8"))
    end = start + timedelta(hours=hours)
    visits = plan_visits(priors, end, seed, closures)
    out = root / scenario
    counts = {"frames": 0, "files": 0}
    for h in range(hours):
        hour = start + timedelta(hours=h)
        rows = frames_for_hour(visits, hour, priors, seed, scenario)
        path = out / f"{hour:%Y-%m-%d}" / f"{hour:%H}.jsonl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        counts["frames"] += len(rows)
        counts["files"] += 1
    in_window = [v for v in visits if v.end > start and v.start < end]
    truth_path = out / "ground_truth_port_calls.jsonl"
    truth_path.write_text(
        "".join(json.dumps(ground_truth(v, scenario)) + "\n" for v in in_window), encoding="utf-8"
    )
    dwell = [
        ground_truth(v, scenario)["vessel_dwell_h"] for v in in_window if not v.truth["lighterage"]
    ]
    manifest = {
        "scenario_id": scenario,
        "generator": GENERATOR,
        "seed": seed,
        "is_synthetic": True,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "closures": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in closures],
        "priors": str(priors_path.relative_to(repo_root())),
        "priors_sha256": hashlib.sha256(priors_path.read_bytes()).hexdigest(),
        "visits_in_window": len(in_window),
        **counts,
        "check_dwell_h_non_lighterage": {
            "p50": round(statistics.median(dwell), 1) if dwell else None,
            "p90": round(statistics.quantiles(dwell, n=10)[-1], 1) if len(dwell) >= 10 else None,
        },
    }
    (out / "scenario.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _closure(text: str) -> tuple[datetime, datetime]:
    when, hours = text.split(",")
    start = datetime.fromisoformat(when).replace(tzinfo=UTC)
    return start, start + timedelta(hours=float(hours))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ais-synth", description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--start", help="UTC ISO start (default: 7 days before this hour)")
    parser.add_argument("--hours", type=int, default=168)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--closure",
        action="append",
        default=[],
        metavar="ISO_START,HOURS",
        help="port closed to river transits (repeatable)",
    )
    args = parser.parse_args(argv)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = (
        datetime.fromisoformat(args.start).replace(tzinfo=UTC)
        if args.start
        else now - timedelta(hours=args.hours)
    )
    root = repo_root() / "data" / "synthetic" / "DS-AIS-01"
    manifest = generate(
        args.scenario, start, args.hours, args.seed, [_closure(c) for c in args.closure], root
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
