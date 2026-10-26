"""C1 acceptance on the synthetic world (needs sim and C1 together, so it lives at the root).

C1-AC01 size, C1-AC02 planted single points of failure, C1-AC04 what-if speed and seeds."""

from __future__ import annotations

import time

import pytest
from cportal_c1 import service
from cportal_c1.cascade import Disruption, monte_carlo
from cportal_c1.graph import SupplyGraph, from_records
from cportal_c1.schemas import DisruptionIn, WhatIfRequest
from cportal_sim.world import World, build_world

SEEDS = (42, 7, 11, 23, 99)


@pytest.fixture(scope="module")
def world() -> World:
    return build_world()


@pytest.fixture(scope="module")
def graph(world: World) -> SupplyGraph:
    return from_records(world.records, world.start)


def test_ac01_graph_size(graph: SupplyGraph) -> None:
    edges = {(s.src, s.dst) for s in graph.supplies}
    assert len(graph.nodes) >= 150 and len(graph.supplies) >= 600 and len(edges) >= 300
    industries = {n.industry for n in graph.nodes.values()}
    assert {"garments", "pharma"} <= industries


def test_ac02_planted_spofs_rank_top_10() -> None:
    """Recall of the planted sole sources in each industry's top 10, over five seeds."""
    found = total = 0
    for seed in SEEDS:
        world = build_world(seed=seed)
        graph = from_records(world.records, world.start)
        metrics = service.compute_metrics(graph)
        for spec in world.planted:
            node = str(world.facilities[spec["facility_key"]].id)
            industry = graph.nodes[node].industry
            top = [m.node_id for m in service.rank(metrics, "dominance", industry)[:10]]
            found += node in top
            total += 1
        # The Chattogram gateway carries every export: always the top single point of failure.
        assert service.rank(metrics, "dominance")[0].node_id == graph.gateway
    assert found / total >= 0.9, f"recall {found}/{total}"


def test_ac04_what_if_speed_and_reproducibility(world: World, graph: SupplyGraph) -> None:
    mill_x = str(world.facilities["fabric_mill_3.fabric_mill.3"].id)
    t0 = time.perf_counter()
    out = service.what_if(
        graph, WhatIfRequest(disruptions=[DisruptionIn(node_id=mill_x, duration_d=21)])
    )
    assert time.perf_counter() - t0 < 2.0
    assert out.orders_late > 0 and out.first_impact_d is not None
    disruptions = [Disruption(graph.gateway, duration_d=3)]
    t0 = time.perf_counter()
    runs = monte_carlo(graph, disruptions, 200, seed=5)
    assert time.perf_counter() - t0 < 15.0
    again = monte_carlo(graph, disruptions, 200, seed=5)
    assert [r.revenue_at_risk_usd for r in runs] == [r.revenue_at_risk_usd for r in again]


def test_tts_below_ttr_for_planted_spofs(world: World, graph: SupplyGraph) -> None:
    """C1-AC03: TTS and TTR exist for every supplier, and the planted ones fail TTS < TTR."""
    metrics = {m.node_id: m for m in service.compute_metrics(graph)}
    for spec in world.planted:
        m = metrics[str(world.facilities[spec["facility_key"]].id)]
        assert m.tts_d is not None and m.ttr_d is not None and m.tts_d < m.ttr_d
    suppliers = [m for m in metrics.values() if m.downstream_orders and m.kind == "facility"]
    assert all(m.tts_d is not None and m.ttr_d is not None for m in suppliers)
