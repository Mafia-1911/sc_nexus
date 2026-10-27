"""C3 on a hand-made corridor over the real place coordinates (no OSM extract needed)."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from cportal_c3.network import Edge, RoadNet
from cportal_c3.osm import haversine_m
from cportal_c3.plan import Planner, Request, _next_departure
from cportal_c3.priors import load_priors
from cportal_core.timeutil import DHAKA

P = load_priors()
FACTORS = {
    key: {"id": key, "label": key, "value": value, "year": 2026, "source": "test"}
    for key, value in {"road": 0.078, "reefer": 0.092, "rail": 0.026, "barge": 0.037}.items()
}
WAYPOINTS = {  # extra nodes: a trunk route and a slower secondary detour
    "comilla": (91.18, 23.46),
    "meghna": (90.62, 23.60),
    "detour": (90.95, 23.20),
}


def _xy(key: str) -> tuple[float, float]:
    if key in WAYPOINTS:
        return WAYPOINTS[key]
    spec = P.places[key]
    return float(spec["lon"]), float(spec["lat"])


def _edge(i: int, a: str, b: str, highway: str) -> Edge:
    pa, pb = _xy(a), _xy(b)
    mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
    return Edge(u=hash(a) % 10**9, v=hash(b) % 10**9, length_m=haversine_m(pa, pb) * 1.25,
                highway=highway, maxspeed_kmh=None, coords=(pa, mid, pb))  # fmt: skip


@pytest.fixture(scope="module")
def planner() -> Planner:
    links = [
        ("BDCGP", "comilla", "trunk"),
        ("comilla", "meghna", "trunk"),
        ("meghna", "BDKAM", "trunk"),
        ("BDKAM", "tongi", "primary"),
        ("tongi", "gazipur", "primary"),
        ("comilla", "detour", "secondary"),
        ("detour", "narayanganj", "secondary"),
        ("narayanganj", "BDPGN", "secondary"),
        ("BDPGN", "BDKAM", "primary"),
        ("narayanganj", "tongi", "secondary"),
    ]
    net = RoadNet([_edge(i, a, b, h) for i, (a, b, h) in enumerate(links)], P)
    return Planner(net, P, FACTORS)


def _req(hour: int = 23, hours: float = 72, **kw: object) -> Request:
    depart = datetime(2026, 10, 27, hour, tzinfo=UTC)
    return Request(
        origin="BDCGP",
        dest="gazipur",
        depart=depart,
        deadline=depart + timedelta(hours=hours),
        **kw,
    )  # type: ignore[arg-type]


def test_plans_cover_road_rail_and_barge(planner: Planner) -> None:
    plans = planner.evaluate(_req(), n=200)
    names = [p.name for p in plans]
    assert len(plans) >= 3 and any("rail" in n for n in names) and any("barge" in n for n in names)
    assert sum(1 for p in plans if p.pareto_rank == 0) >= 2  # real trade-offs, not one winner
    road = next(p for p in plans if p.modes == ["road"])
    rail = next(p for p in plans if "rail" in p.modes)
    assert rail.co2e_kg < road.co2e_kg  # rail is the low-carbon option
    assert road.quantile(0.5) < rail.quantile(0.5)  # and the road the fast one
    for p in plans:
        assert p.quantile(0.5) <= p.quantile(0.9) and p.on_time_prob is not None
        assert p.explanation


def test_co2e_is_traceable_to_the_factor_row(planner: Planner) -> None:
    """C3-AC03: CO2e = factor (kg/t·km) × cargo tonnes × km, for every leg, with its source."""
    plan = planner.evaluate(_req(qty_teu=2), n=50)[0]
    tonnes = 2 * float(P["cargo_t_per_teu"])
    for leg in plan.legs:
        if leg.factor is not None:
            assert leg.co2e_kg == pytest.approx(leg.factor["value"] * tonnes * leg.km)
            assert leg.factor["source"] and leg.factor["year"]


def test_truck_ban_holds_trucks_out_of_central_dhaka(planner: Planner) -> None:
    """C3-AC06: no plan drives into the ban zone while it is closed."""
    path = planner.road_options("BDPGN", "BDKAM", _req().depart)[0][1]  # inside the zone
    start, end, _, _ = P.truck_ban()
    day = planner.net.traverse(path, datetime(2026, 10, 27, start + 2, tzinfo=DHAKA))
    night = planner.net.traverse(path, datetime(2026, 10, 27, end, tzinfo=DHAKA))
    assert day.ban_wait_h > 0 and night.ban_wait_h == 0
    assert day.hours >= day.ban_wait_h
    # The ban follows Dhaka clocks whatever zone the caller uses (UTC 02:00 is 08:00 local).
    utc_night = datetime(2026, 10, 27, end, tzinfo=DHAKA).astimezone(UTC)
    assert planner.net.traverse(path, utc_night).ban_wait_h == 0


def test_reefer_cargo_stays_on_the_road(planner: Planner) -> None:
    plans = planner.evaluate(_req(reefer=True), n=50)
    assert plans and all(p.modes == ["road"] for p in plans)
    dry = planner.evaluate(_req(), n=50)
    assert min(p.cost_bdt for p in plans) > min(p.cost_bdt for p in dry if p.modes == ["road"])


def test_timetables_cancel_and_respect_weekdays() -> None:
    rng = random.Random(1)
    barge = P["services"]["barge_cgp_pgn"]
    monday = datetime(2026, 10, 26, 12, tzinfo=UTC)  # after Monday's 10:00 sailing
    nxt = _next_departure(barge, monday, rng)
    assert nxt.weekday() in barge["departures_weekdays"] and nxt > monday
    always_off = {**P["services"]["rail_cgp_kam"], "cancel_prob": 0.999}
    late = _next_departure(always_off, monday, random.Random(2))
    assert late - monday > timedelta(days=2)  # skipped many cancelled trains


def test_on_time_probability_is_calibrated(planner: Planner) -> None:
    """C3-AC04 on synthetic ground truth: predicted P(on time) vs outcomes from fresh draws."""
    errors = []
    for hours in (12, 24, 36, 48, 72):
        req = _req(hours=hours)
        plan = planner.evaluate(req, n=300, seed=3)[0]
        truth = planner.simulate(plan, req.depart, 300, seed=99)
        observed = sum(t <= hours for t in truth) / len(truth)
        errors.append(abs((plan.on_time_prob or 0) - observed))
    assert max(errors) <= 0.1


def test_same_seed_same_answer(planner: Planner) -> None:
    a = [p.quantile(0.5) for p in planner.evaluate(_req(), n=100, seed=5)]
    b = [p.quantile(0.5) for p in planner.evaluate(_req(), n=100, seed=5)]
    assert a == b


def test_departure_sweep(planner: Planner) -> None:
    req = _req(hour=8, hours=30)
    plan = planner.evaluate(req, n=100)[0]
    sweep = planner.sweep(plan, req)
    assert (
        len(sweep) == int(P["departure_sweep"]["hours"]) // int(P["departure_sweep"]["step_h"]) + 1
    )
    assert all("p90_h" in row and "on_time_prob" in row for row in sweep)
