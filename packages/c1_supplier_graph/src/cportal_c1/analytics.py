"""Structural analytics (C1 §5, L0): who depends on whom, and what breaks if a node fails.

**Single points of failure.** A plant needs *every* input of a product (AND) and can take each
input from *any* qualified supplier (OR). A dominator tree over the plain facility graph treats
all in-edges as OR, so it misses a sole label supplier whose plant still has fabric. We run the
removal test instead: drop node j, recompute which (plant, product) pairs can still be made
(least fixpoint over the AND/OR graph), and the open orders that become impossible are the ones
j dominates. On an OR-only graph this is exactly the dominator relation (ADR-016).

Transshipment hubs are substitutable (cargo reroutes at a delay), so they never dominate;
the Chattogram gateway carries every sea import and every export, so it can.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise

import networkx as nx

from cportal_c1.graph import SupplyGraph


def producible(g: SupplyGraph, removed: frozenset[str]) -> set[tuple[str, str]]:
    """(facility, product) pairs that can still be made with `removed` nodes down."""
    blocking = {n for n in removed if g.nodes.get(n) is None or g.nodes[n].type != "hub"}
    pairs = [(f, p) for f, products in g.makes.items() for p in products if f not in blocking]
    ok: set[tuple[str, str]] = set()
    changed = True
    while changed:
        changed = False
        for f, p in pairs:
            if (f, p) in ok:
                continue
            if all(_input_ok(g, f, c, ok, blocking) for c in g.bom.get(p, {})):
                ok.add((f, p))
                changed = True
    return ok


def _input_ok(g: SupplyGraph, f: str, c: str, ok: set[tuple[str, str]], blocking: set[str]) -> bool:
    suppliers = g.inbound.get((f, c))
    if not suppliers:  # not modelled for this plant: assume available
        return True
    return any(
        s.src not in blocking and (s.src, c) in ok and not blocking.intersection(s.route)
        for s in suppliers
    )


def feasible_orders(g: SupplyGraph, removed: frozenset[str]) -> set[str]:
    if g.gateway in removed:
        return set()  # nothing ships
    ok = producible(g, removed)
    return {o.id for o in g.orders if (o.facility, o.product) in ok}


@dataclass(frozen=True)
class Structure:
    downstream_orders: dict[str, list[str]]
    dominated_orders: dict[str, list[str]]
    hhi_inputs: dict[str, dict[str, float]]
    single_sourced_inputs: dict[str, list[str]]
    sole_source_for: dict[str, list[dict[str, str]]]
    betweenness: dict[str, float]
    pagerank_rev: dict[str, float]


def structure(g: SupplyGraph) -> Structure:
    downstream: dict[str, list[str]] = defaultdict(list)
    for oid, deps in g.order_deps.items():
        for n in deps:
            downstream[n].append(oid)
    baseline = feasible_orders(g, frozenset())
    own = {o.id: o.facility for o in g.orders}
    dominated: dict[str, list[str]] = {}
    for node, orders in downstream.items():
        if g.nodes.get(node) is not None and g.nodes[node].type == "hub":
            dominated[node] = []
            continue
        still = feasible_orders(g, frozenset({node}))
        # A plant trivially "dominates" its own orders; the question is what breaks elsewhere.
        dominated[node] = [o for o in orders if o in baseline and o not in still and own[o] != node]
    hhi: dict[str, dict[str, float]] = defaultdict(dict)
    single: dict[str, list[str]] = defaultdict(list)
    sole: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (f, c), suppliers in g.inbound.items():
        hhi[f][c] = round(sum(s.share**2 for s in suppliers), 4)
        if len(suppliers) == 1:
            single[f].append(c)
            if g.need.get((f, c), 0.0) > 0:
                sole[suppliers[0].src].append({"consumer": f, "product": c})
    graph = network(g)
    return Structure(
        downstream_orders=dict(downstream),
        dominated_orders=dominated,
        hhi_inputs=dict(hhi),
        single_sourced_inputs={k: sorted(v) for k, v in single.items()},
        sole_source_for=dict(sole),
        betweenness=nx.betweenness_centrality(graph, normalized=True),
        pagerank_rev=nx.pagerank(graph.reverse(copy=True), weight="value_usd_d"),
    )


def network(g: SupplyGraph) -> nx.DiGraph:
    """Material and export flows as one directed graph, weighted by daily value: supplier →
    (hub → gateway) → plant, and plant → gateway → buyer DC."""
    graph = nx.DiGraph()
    graph.add_nodes_from(g.nodes)

    def add(a: str, b: str, value: float) -> None:
        if graph.has_edge(a, b):
            graph[a][b]["value_usd_d"] += value
        else:
            graph.add_edge(a, b, value_usd_d=value)

    for s in g.supplies:
        value = g.flow(s) * g.products[s.product].unit_value_usd + 1e-9
        hops = [s.src, *s.route, s.dst]
        for a, b in pairwise(hops):
            add(a, b, value)
    for o in g.orders:
        value = o.revenue_usd / g.priors.horizon_d
        add(o.facility, g.gateway, value)
        if o.customer:
            add(g.gateway, o.customer, value)
    return graph
