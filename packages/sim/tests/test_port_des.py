"""Port DES invariants (02 §12: property checks on generators) and its tie to real berths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from cportal_connectors.registry import connectors
from cportal_core.schemas.records import PortZoneRecord
from cportal_sim.port_des import DesResult, PortDES, load_priors, simulate, state_at

END = datetime(2026, 10, 26, tzinfo=UTC)
START = END - timedelta(days=21)
CLOSURE = (END - timedelta(days=8), END - timedelta(days=6, hours=6))


@pytest.fixture(scope="module")
def runs() -> tuple[DesResult, DesResult]:
    return simulate(START, END, seed=7), simulate(START, END, seed=7, closures=[CLOSURE])


def test_visit_invariants(runs: tuple[DesResult, DesResult]) -> None:
    for result in runs:
        assert result.visits
        for v in result.visits:
            assert v.leave_anchorage >= v.arrive and v.depart >= v.leave_anchorage
            assert v.dwell_h >= 0 and v.waiting_h >= 0
            if v.mode == "berth":
                assert v.berth_start and v.berth_end and v.berth_code
                assert v.arrive <= v.leave_anchorage <= v.berth_start <= v.berth_end


def test_a_berth_holds_one_vessel_at_a_time(runs: tuple[DesResult, DesResult]) -> None:
    for result in runs:
        by_berth: dict[str, list[tuple[datetime, datetime]]] = {}
        for v in result.visits:
            if v.berth_code and v.berth_start and v.berth_end:
                by_berth.setdefault(v.berth_code, []).append((v.berth_start, v.berth_end))
        for spans in by_berth.values():
            spans.sort()
            for (_, end), (start, _) in pairwise(spans):
                assert start >= end


def test_nothing_moves_during_a_closure(runs: tuple[DesResult, DesResult]) -> None:
    _, closed = runs
    a, b = CLOSURE
    for v in closed.visits:
        if v.mode == "berth":
            assert not (a < v.leave_anchorage < b)
            assert v.berth_end and not (a < v.berth_end < b)


def test_deep_vessels_move_on_high_water() -> None:
    priors = load_priors()
    des = PortDES(priors, 3, START, END)
    result = des.run()
    deep = [v for v in result.visits if v.mode == "berth" and v.vessel.draught > des.deep]
    assert deep
    for v in deep:
        # The channel slot starts inside the window; the recorded time is after the slot.
        start_h = des.h(v.leave_anchorage) - des.slot_h
        assert des.tide_open(start_h) == pytest.approx(start_h)


def test_common_random_numbers(runs: tuple[DesResult, DesResult]) -> None:
    """Same seed with and without a closure: identical vessels and identical history before
    the closure, so a scenario's effect is the disruption's alone."""
    open_, closed = runs
    before = [v for v in open_.visits if v.depart < CLOSURE[0]]
    closed_by_index = {v.index: v for v in closed.visits}
    assert before
    for v in before:
        w = closed_by_index[v.index]
        assert (w.arrive, w.leave_anchorage, w.depart) == (v.arrive, v.leave_anchorage, v.depart)
    assert {v.index for v in open_.visits} == set(closed_by_index)


def test_occupancy_never_exceeds_capacity(runs: tuple[DesResult, DesResult]) -> None:
    for result in runs:
        ts = START
        while ts < END:
            for pool in state_at(result, ts)["berth_occupancy"].values():
                assert pool["occupied"] <= pool["berths"]
            ts += timedelta(hours=12)


def test_des_berths_are_real_cpa_berths() -> None:
    real = {r.name for r in connectors()["DS-PORT-07"].replay() if isinstance(r, PortZoneRecord)}
    for codes in load_priors()["berths"].values():
        assert set(codes) <= real
