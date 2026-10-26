"""C1 on a network small enough to check by hand (tests/c1_tiny.py)."""

from __future__ import annotations

import pytest
from c1_tiny import AS_OF, build, node
from cportal_c1 import service
from cportal_c1.analytics import feasible_orders, structure
from cportal_c1.cascade import Disruption, monte_carlo, simulate
from cportal_c1.exposure import ExposureModel
from cportal_c1.graph import SupplyGraph, from_records
from cportal_c1.schemas import DisruptionIn, WhatIfRequest

GATEWAY = "port:BDCGP"


@pytest.fixture(scope="module")
def g() -> SupplyGraph:
    return from_records(build(), AS_OF)


def test_graph_is_assembled(g: SupplyGraph) -> None:
    assert {n for n in g.nodes if n.startswith("port:")} >= {GATEWAY, "port:SGSIN"}
    assert len(g.supplies) == 5 and len(g.orders) == 2
    sea = next(s for s in g.supplies if s.mode == "sea")
    assert sea.route == ("port:SGSIN", GATEWAY)  # Shaoxing imports transship at Singapore
    assert g.need[(node("P1"), "G-LABEL")] == pytest.approx(100.0)  # 12 000 tees / 120 d


def test_and_or_dominance(g: SupplyGraph) -> None:
    """A tee needs fabric AND labels; fabric may come from either mill."""
    s = structure(g)
    orders = {o.facility: o.id for o in g.orders}
    assert set(s.dominated_orders[node("T1")]) == set(orders.values())  # sole label source
    assert s.dominated_orders[node("M1")] == []  # M2 also supplies P1
    assert s.dominated_orders[node("O1")] == [orders[node("P2")]]
    assert set(s.dominated_orders[GATEWAY]) == set(orders.values())  # every export
    assert s.dominated_orders["port:SGSIN"] == []  # hubs reroute
    assert s.dominated_orders[node("P1")] == []  # own orders are not "dominated elsewhere"
    assert feasible_orders(g, frozenset({node("M1"), node("M2")})) == {orders[node("P2")]}


def test_concentration(g: SupplyGraph) -> None:
    s = structure(g)
    assert s.hhi_inputs[node("P1")]["G-FABRIC"] == pytest.approx(0.5)
    assert s.single_sourced_inputs[node("P2")] == ["G-FABRIC", "G-LABEL"]
    assert {x["consumer"] for x in s.sole_source_for[node("T1")]} == {node("P1"), node("P2")}


def test_tts_from_the_lp(g: SupplyGraph) -> None:
    m = ExposureModel(g)
    assert m.tts(frozenset()) == pytest.approx(g.priors.tts_cap_d)  # healthy network
    assert m.tts(frozenset({node("T1")})) == pytest.approx(5.0, abs=0.01)  # P1's label cover
    assert m.tts(frozenset({node("O1")})) == pytest.approx(3.0, abs=0.01)  # P2's fabric cover
    # M2's spare capacity covers 0.5 × 1.3 = 65 % of P1's fabric; 10 days of stock bridge the
    # other 35 % for 10 / 0.35 ≈ 28.6 days.
    assert m.tts(frozenset({node("M1")})) == pytest.approx(10 / 0.35, abs=0.05)
    assert m.tts(frozenset({GATEWAY})) == 0.0
    exp = m.exposure(node("T1"))
    assert exp.ttr_source == "prior" and exp.ttr_d > exp.tts_d and exp.performance_impact_usd > 0


def test_short_outage_is_absorbed_and_long_one_is_not(g: SupplyGraph) -> None:
    short = simulate(g, [Disruption(node("T1"), duration_d=3)])
    assert short.first_impact_d is None and not short.impacts
    long = simulate(g, [Disruption(node("T1"), duration_d=20)])
    # Labels run out after 5 days of stock plus the 2 days already on the road.
    assert long.first_impact_d == pytest.approx(7, abs=1)
    assert long.recovery_d is not None and long.recovery_d > 20
    assert {i.facility for i in long.impacts} <= {node("P1"), node("P2")}


def test_alternative_supplier_absorbs_the_loss(g: SupplyGraph) -> None:
    out = simulate(g, [Disruption(node("M1"), duration_d=21)])
    assert not out.late  # M2's spare capacity plus P1's stock carry it


def test_gateway_closure_delays_exports(g: SupplyGraph) -> None:
    out = simulate(g, [Disruption(GATEWAY, duration_d=40)])
    assert out.first_impact_d == 0.0 and out.impacts
    assert all(i.cause in ("gateway", "inputs") for i in out.impacts)


def test_monte_carlo_is_reproducible(g: SupplyGraph) -> None:
    runs = [Disruption(node("T1"), duration_d=10)]
    a = [r.revenue_at_risk_usd for r in monte_carlo(g, runs, 20, seed=3)]
    b = [r.revenue_at_risk_usd for r in monte_carlo(g, runs, 20, seed=3)]
    assert a == b


def test_metrics_drivers_are_exact_shapley_values(g: SupplyGraph) -> None:
    metrics = service.compute_metrics(g)
    scored = [m for m in metrics if m.risk_score is not None]
    mean = sum(m.risk_score or 0 for m in scored) / len(scored)
    for m in scored:
        total = sum(d.contribution for d in m.risk_drivers)
        assert (m.risk_score or 0) - mean == pytest.approx(total, abs=0.05)
    top = service.rank(metrics, "dominance")[0]
    assert top.node_id in (GATEWAY, node("T1"))
    assert all(m.type != "customer_site" for m in service.rank(metrics, "risk"))


def test_what_if_service(g: SupplyGraph) -> None:
    req = WhatIfRequest(disruptions=[DisruptionIn(node_id=node("T1"), duration_d=20)], mc_runs=10)
    out = service.what_if(g, req)
    assert out.tts_d == pytest.approx(5.0, abs=0.01)
    assert out.revenue_at_risk_usd_p90 is not None
    assert out.revenue_at_risk_usd_p90 >= (out.revenue_at_risk_usd_p50 or 0)
    assert any(m.action_type == "dual_source" for m in out.mitigations)
    with pytest.raises(KeyError):
        service.what_if(g, WhatIfRequest(disruptions=[DisruptionIn(node_id="x", duration_d=1)]))


def test_defaults_come_from_priors_without_events(g: SupplyGraph) -> None:
    d = service.whatif_defaults(g, node("M1"))
    assert d.duration_d == g.priors.ttr("fabric_mill")[0] and d.capacity_pct == 0
