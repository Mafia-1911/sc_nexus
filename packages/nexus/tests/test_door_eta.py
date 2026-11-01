"""Door ETA Monte Carlo (08 §1, NX-R01, NX-AC02): pure, no database."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
from cportal_nexus.door_eta import Hold, Leg, Priors, due_time, simulate, split_lognormal

NOW = datetime(2026, 10, 26, tzinfo=UTC)
CALM = Priors(leg_sigma={"road": 1e-6, "sea": 1e-6}, container_dwell_h=(96.0, 96.0001))
NOISY = Priors(leg_sigma={"road": 0.25, "sea": 0.12}, container_dwell_h=(96.0, 192.0))
VESSEL = [{"p10": 42.0, "p50": 110.0, "p90": 296.0}, {"p10": 30.0, "p50": 90.0, "p90": 240.0}]


def h(x: float) -> datetime:
    return NOW + timedelta(hours=x)


def export(**kw: object) -> list[Leg]:
    """Factory → Chattogram (road), Chattogram → Colombo (sea), Colombo → DC (sea)."""
    return [
        Leg(1, "road", "BDGAZ", "BDCGP", h(2), h(12), **kw),  # type: ignore[arg-type]
        Leg(2, "sea", "BDCGP", "LKCMB", h(120), h(192)),
        Leg(3, "sea", "LKCMB", "NLRTM", h(240), h(600)),
    ]


def test_split_lognormal_is_exact_at_its_quantiles() -> None:
    z = np.array([-1.2816, 0.0, 1.2816])
    assert np.allclose(split_lognormal(42.0, 110.0, 296.0, z), [42.0, 110.0, 296.0], rtol=1e-3)


def test_on_plan_without_noise_lands_on_the_plan() -> None:
    eta = simulate(export(), NOW, due_time(date(2026, 11, 30)), CALM, [])
    assert abs((eta.p50 - h(600)).total_seconds()) < 60
    assert eta.on_time_prob == 1.0


def test_fixed_seed_is_deterministic() -> None:
    a = simulate(export(), NOW, None, NOISY, VESSEL, seed=7)
    b = simulate(export(), NOW, None, NOISY, VESSEL, seed=7)
    assert (a.p10, a.p50, a.p90, a.drivers) == (b.p10, b.p50, b.p90, b.drivers)


def test_quantiles_are_ordered_and_never_early_against_the_schedule() -> None:
    eta = simulate(export(), NOW, None, NOISY, VESSEL)
    assert eta.p10 <= eta.p50 <= eta.p90
    # A leg never leaves before its planned departure, so P10 is at most a little early (moving
    # time noise on the last leg only).
    assert eta.p10 >= h(240) + timedelta(hours=360 * 0.6)


def test_a_port_closure_during_the_stay_delays_the_door_and_is_a_driver() -> None:
    due = due_time(date(2026, 11, 20))  # ≈ 25 days of slack against a 25-day plan
    calm = simulate(export(), NOW, due, NOISY, VESSEL)
    hold = Hold("Cyclone SYN-01: port closed", "BDCGP", h(20), p50_h=42.0, p90_h=60.0)
    hit = simulate(export(), NOW, due, NOISY, VESSEL, holds=[hold])
    assert hit.p50 > calm.p50 + timedelta(hours=24)
    assert (hit.on_time_prob or 0) < (calm.on_time_prob or 0)
    assert dict(hit.drivers)["Cyclone SYN-01: port closed"] > 30


def test_a_closure_elsewhere_or_after_departure_changes_nothing() -> None:
    base = simulate(export(), NOW, None, NOISY, VESSEL)
    away = Hold("closure", "BDMGL", h(20), 42.0, 60.0)
    late = Hold("closure", "BDCGP", h(2000), 42.0, 60.0)
    assert simulate(export(), NOW, None, NOISY, VESSEL, holds=[away, late]).p50 == base.p50


def test_completed_legs_fix_the_clock() -> None:
    done = [
        Leg(1, "road", "BDGAZ", "BDCGP", h(-300), h(-290), h(-300), h(-290)),
        Leg(2, "sea", "BDCGP", "NLRTM", h(-200), h(-10), h(-200), h(-12)),
    ]
    eta = simulate(done, NOW, None, NOISY, VESSEL)
    assert eta.p10 == eta.p90 == NOW  # delivered before now: the clock never runs backwards
