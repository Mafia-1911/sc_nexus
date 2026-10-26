"""`uv run calibrate`: compare the port DES with real marginals and write CALIBRATION.md (03 §4).

Real targets are computed live from the replayed canonical records (committed samples), so the
report is reproducible offline:
- arrivals per day by type: DS-PORT-01 PortWatch, Chattogram;
- port-visit duration of cargo vessels (confidence 4, ≤ 60 days, no window overlap): DS-AIS-02;
- cargo vessels present in the outer anchorage per day: DS-AIS-02 4Wings presence;
- days from arrival to berthing by berth class: DS-PORT-07 CPA berthing report.

`--search` runs a small seeded grid over the lighter and lighterage knobs and prints the best
setting; the chosen values are copied into config/priors/port_des.yaml by a person, with a note.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_connectors.registry import connectors
from cportal_core.ids import port_id
from cportal_core.paths import cards_dir
from cportal_core.schemas.records import (
    PortActivityDailyRecord,
    PortCallRecord,
    PortZoneRecord,
    VesselRecord,
    ZonePresenceDailyRecord,
)

from cportal_sim.port_des import OCEAN_TYPES, DesResult, load_priors, present_on, simulate

WINDOW_DAYS = 90
SEEDS = (11, 23, 42)


def quantile(xs: list[float], p: float) -> float:
    s = sorted(xs)
    if not s:
        return math.nan
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def ks_statistic(a: list[float], b: list[float]) -> float:
    """Two-sample Kolmogorov–Smirnov D (max distance between empirical CDFs)."""
    a, b = sorted(a), sorted(b)
    i = j = 0
    d = 0.0
    while i < len(a) and j < len(b):
        x = min(a[i], b[j])
        while i < len(a) and a[i] <= x:
            i += 1
        while j < len(b) and b[j] <= x:
            j += 1
        d = max(d, abs(i / len(a) - j / len(b)))
    return d


@dataclass
class Targets:
    arrivals_mean: dict[str, float]
    arrivals_sd: dict[str, float]
    dwell_h: list[float]
    presence: list[int]
    cpa_wait_d: dict[str, list[float]]
    sources: dict[str, str]


def real_targets() -> Targets:
    c = connectors()
    ctg = port_id("BDCGP")
    pw = [
        r
        for r in c["DS-PORT-01"].replay()
        if isinstance(r, PortActivityDailyRecord) and r.port_id == ctg
    ]
    arrivals = {t: [float(r.calls_by_type.get(t, 0)) for r in pw] for t in OCEAN_TYPES}
    gfw = c["DS-AIS-02"].replay()
    cargo = {r.id for r in gfw if isinstance(r, VesselRecord) and r.ship_type_group == "cargo"}
    dwell = [
        float(r.dwell_h)
        for r in gfw
        if isinstance(r, PortCallRecord)
        and r.port_id == ctg
        and r.dwell_h is not None
        and r.dwell_h <= 1440
        and r.confidence == 4
        and "window_overlap" not in r.quality_flags
        and r.vessel_id in cargo
    ]
    per_day: dict[Any, set[Any]] = defaultdict(set)
    for r in gfw:
        if isinstance(r, ZonePresenceDailyRecord) and r.ship_type_group == "cargo":
            per_day[r.date].add(r.mmsi or r.imo)
    cpa = c["DS-PORT-07"].replay()
    zones: dict[Any, Any] = {
        r.id: r.attrs.get("berth_class") for r in cpa if isinstance(r, PortZoneRecord)
    }
    waits: dict[str, list[float]] = defaultdict(list)
    for r in cpa:
        if (
            isinstance(r, PortCallRecord)
            and r.waiting_h is not None
            and "long_stay" not in r.quality_flags
        ):
            waits[str(zones.get(r.berth_zone_id))].append(r.waiting_h / 24)
    return Targets(
        arrivals_mean={t: statistics.mean(x) for t, x in arrivals.items()},
        arrivals_sd={t: statistics.pstdev(x) for t, x in arrivals.items()},
        dwell_h=dwell,
        presence=[len(v) for v in per_day.values()],
        cpa_wait_d=dict(waits),
        sources={
            "arrivals": f"DS-PORT-01 PortWatch, Chattogram, {len(pw)} days",
            "dwell": f"DS-AIS-02 GFW port visits, cargo, confidence 4, ≤ 60 d: n={len(dwell)}",
            "presence": f"DS-AIS-02 GFW 4Wings presence, cargo, {len(per_day)} days",
            "cpa": "DS-PORT-07 CPA berthing report 2026-01-05 (vessels at berth only)",
        },
    )


@dataclass
class Metrics:
    arrivals_mean: dict[str, float]
    dwell_h: list[float]
    presence: list[int]
    berth_wait_d: dict[str, list[float]]


POOL_CLASS = {"container": "container_terminal", "gcb": "general_cargo_jetty", "oil": "oil_jetty"}


def des_metrics(result: DesResult) -> Metrics:
    start, end = result.start, result.end
    window = [v for v in result.visits if start <= v.arrive < end]
    days = [start + timedelta(days=i) for i in range((end - start).days)]
    arrivals = {t: sum(1 for v in window if v.kind == t) / max(len(days), 1) for t in OCEAN_TYPES}
    waits: dict[str, list[float]] = defaultdict(list)
    for v in window:
        if v.mode == "berth" and v.berth_pool:
            waits[POOL_CLASS[v.berth_pool]].append(v.waiting_h / 24)
    return Metrics(
        arrivals_mean=arrivals,
        dwell_h=[v.dwell_h for v in window if v.dwell_h <= 1440],
        presence=[len(present_on(result, d)) for d in days],
        berth_wait_d=dict(waits),
    )


def run(priors: dict[str, Any], seeds: tuple[int, ...] = SEEDS) -> Metrics:
    end = datetime(2026, 10, 26, tzinfo=UTC)
    start = end - timedelta(days=WINDOW_DAYS)
    merged = Metrics({}, [], [], defaultdict(list))
    arrivals: dict[str, list[float]] = defaultdict(list)
    for seed in seeds:
        m = des_metrics(simulate(start, end, seed=seed, priors=priors))
        merged.dwell_h += m.dwell_h
        merged.presence += m.presence
        for k, v in m.berth_wait_d.items():
            merged.berth_wait_d[k] += v
        for k, a in m.arrivals_mean.items():
            arrivals[k].append(a)
    merged.arrivals_mean = {k: statistics.mean(v) for k, v in arrivals.items()}
    return merged


def loss(m: Metrics, t: Targets) -> float:
    terms = [
        abs(math.log(quantile(m.dwell_h, 0.5) / quantile(t.dwell_h, 0.5))),
        abs(math.log(quantile(m.dwell_h, 0.9) / quantile(t.dwell_h, 0.9))),
        0.5 * abs(math.log(quantile(m.dwell_h, 0.1) / quantile(t.dwell_h, 0.1))),
        abs(math.log(statistics.mean(m.dwell_h) / statistics.mean(t.dwell_h))),
        abs(math.log(statistics.mean(m.presence) / statistics.mean(t.presence))),
    ]
    return sum(terms)


# Centred on the values in config/priors/port_des.yaml (the scale multiplies its medians).
KNOBS = {
    "lighters.per_day": [5.5, 6.0, 6.5, 7.0, 7.5],
    "lighters.stay.median": [55.0, 65.0, 75.0, 85.0],
    "lighters.stay.sigma": [0.8, 0.9, 1.0],
    "lighter_work_scale": [0.8, 1.0, 1.2],
}


def apply(priors: dict[str, Any], setting: dict[str, float]) -> dict[str, Any]:
    p = copy.deepcopy(priors)
    p["lighters"]["per_day"] = setting["lighters.per_day"]
    p["lighters"]["stay"]["median"] = setting["lighters.stay.median"]
    p["lighters"]["stay"]["sigma"] = setting["lighters.stay.sigma"]
    for spec in p["handling"].values():
        if "lighter_work" in spec:
            spec["lighter_work"]["median"] *= setting["lighter_work_scale"]
    return p


def search(t: Targets) -> tuple[dict[str, float], float]:
    base = load_priors()
    best: tuple[dict[str, float], float] | None = None
    for values in itertools.product(*KNOBS.values()):
        setting = dict(zip(KNOBS, values, strict=True))
        score = loss(run(apply(base, setting)), t)
        if best is None or score < best[1]:
            best = (setting, score)
    assert best is not None
    return best


def _row(name: str, real: float, synth: float, unit: str = "") -> str:
    ratio = synth / real if real else math.nan
    return f"| {name} | {real:.2f}{unit} | {synth:.2f}{unit} | {ratio:.2f} |"


def report(t: Targets, m: Metrics, generated: str) -> str:
    def qrow(name: str, p: float) -> str:
        return _row(name, quantile(t.dwell_h, p), quantile(m.dwell_h, p), " h")

    lines = [
        "# Calibration report: port DES v0 vs real marginals",
        "",
        f"_Generated by `make calibrate` ({generated}). Real targets are computed from the "
        "committed replay samples; the DES runs 90 days with seeds "
        f"{', '.join(map(str, SEEDS))} pooled. Regenerate after any change to "
        "`config/priors/port_des.yaml`._",
        "",
        "## Arrivals per day (ocean-going, Chattogram)",
        "",
        "| Type | Real | DES | DES / real |",
        "|---|---|---|---|",
        *(_row(k, t.arrivals_mean[k], m.arrivals_mean.get(k, 0.0)) for k in OCEAN_TYPES),
        "",
        f"Real: {t.sources['arrivals']}; real sd per day: "
        + ", ".join(f"{k} {t.arrivals_sd[k]:.2f}" for k in OCEAN_TYPES)
        + ".",
        "",
        "## Port-visit duration of cargo vessels (D-04 dwell)",
        "",
        "| Statistic | Real | DES | DES / real |",
        "|---|---|---|---|",
        qrow("p10", 0.1),
        qrow("p50", 0.5),
        qrow("p90", 0.9),
        _row("mean", statistics.mean(t.dwell_h), statistics.mean(m.dwell_h), " h"),
        "",
        f"KS statistic D = {ks_statistic(t.dwell_h, m.dwell_h):.3f} "
        f"(n real {len(t.dwell_h)}, n DES {len(m.dwell_h)}). Real: {t.sources['dwell']}. "
        "DES visits are ocean vessels plus lighters, the population GFW labels `cargo`.",
        "",
        "## Cargo vessels present in the outer anchorage per day",
        "",
        "| Statistic | Real | DES | DES / real |",
        "|---|---|---|---|",
        _row("mean", statistics.mean(t.presence), statistics.mean(m.presence)),
        _row("min", float(min(t.presence)), float(min(m.presence))),
        _row("max", float(max(t.presence)), float(max(m.presence))),
        "",
        f"Real: {t.sources['presence']}.",
        "",
        "## Days from arrival to berthing, by berth class",
        "",
        "| Berth class | Real median (n) | DES median (n) |",
        "|---|---|---|",
    ]
    for cls in ("container_terminal", "general_cargo_jetty", "oil_jetty"):
        real = t.cpa_wait_d.get(cls, [])
        synth = m.berth_wait_d.get(cls, [])
        r = f"{quantile(real, 0.5):.1f} ({len(real)})" if real else "—"
        s = f"{quantile(synth, 0.5):.1f} ({len(synth)})" if synth else "—"
        lines.append(f"| {cls} | {r} | {s} |")
    lines += [
        "",
        f"Real: {t.sources['cpa']}. The CPA report lists vessels already at berth, so its waits "
        "are biased low (vessels still at the anchorage are missing) and its 'arrival' may be the "
        "inner-anchorage date; the DES counts from arrival at the outer anchorage. More daily "
        "reports (data/inbox/DS-PORT-07/) will tighten this.",
        "",
        "## Not calibrated yet",
        "",
        "- Eid slowdowns and yard-congestion feedback (03 §4) are not modelled in v0.",
        "- Closure response (cyclone) follows CPA practice in outline only: all work stops; "
        "vessels stay at the anchorage. Remal (May 2024) is the backtest case for M6.",
        "- SAR detections per pass (real 50–251, DS-SAT-04) are emitted by the twin from DES "
        "presence and checked only for range.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calibrate", description=__doc__.split("\n")[0])
    parser.add_argument("--search", action="store_true", help="grid-search the DES knobs")
    args = parser.parse_args(argv)
    targets = real_targets()
    if args.search:
        setting, score = search(targets)
        print(f"best loss {score:.3f}: {setting}")
        return 0
    metrics = run(load_priors())
    print(f"loss {loss(metrics, targets):.3f}")
    path = cards_dir() / "CALIBRATION.md"
    generated = datetime.now(UTC).strftime("%Y-%m-%d")
    path.write_text(report(targets, metrics, generated), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
