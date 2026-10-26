"""C1 public API (02 §6): node metrics, rankings and what-ifs over a `SupplyGraph`.

The API and the worker call these; nothing here touches the database (see `store`).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from cportal_c1 import MODEL_VERSION
from cportal_c1.analytics import Structure, structure
from cportal_c1.cascade import Disruption, Outcome, monte_carlo, simulate
from cportal_c1.exposure import Exposure, ExposureModel
from cportal_c1.graph import EventLink, SupplyGraph
from cportal_c1.priors import Priors
from cportal_c1.risk import LABELS, Scored, features, score
from cportal_c1.schemas import (
    DisruptionIn,
    Driver,
    Mitigation,
    NodeMetrics,
    OrderImpactOut,
    WhatIfRequest,
    WhatIfResult,
)

METRICS = ("dominance", "downstream", "tts_gap", "risk")


@dataclass(frozen=True)
class _Row:
    downstream: list[str]
    dominated: list[str]
    downstream_value: float
    dominated_value: float
    exposure: Exposure | None


def compute_metrics(g: SupplyGraph) -> list[NodeMetrics]:
    """Every node's dependency analytics, TTS/TTR and risk score with drivers."""
    st = structure(g)
    model = ExposureModel(g)
    value = {o.id: o.revenue_usd for o in g.orders}
    product_of = {o.id: o.product for o in g.orders}
    industry_value: dict[str | None, float] = defaultdict(float)
    for o in g.orders:
        industry_value[g.order_industry(o)] += o.revenue_usd
    all_value = sum(value.values())
    rows: dict[str, _Row] = {}
    table: dict[str, dict[str, float]] = {}
    for node_id, node in g.nodes.items():
        downstream = st.downstream_orders.get(node_id, [])
        dominated = st.dominated_orders.get(node_id, [])
        scored = node.type != "customer_site"
        row = _Row(
            downstream=downstream,
            dominated=dominated,
            downstream_value=sum(value[o] for o in downstream),
            dominated_value=sum(value[o] for o in dominated),
            exposure=model.exposure(node_id) if scored and downstream else None,
        )
        rows[node_id] = row
        if scored:
            table[node_id] = features(
                g,
                node_id,
                dominated_value=row.dominated_value,
                downstream_value=row.downstream_value,
                industry_value=industry_value.get(node.industry, 0.0)
                if node.industry
                else all_value,
                tts=row.exposure.tts_d if row.exposure else None,
                ttr=row.exposure.ttr_d if row.exposure else None,
            )
    risk = score(g, table)
    return [
        _metrics(g, node_id, rows[node_id], risk.get(node_id), st, product_of)
        for node_id in g.nodes
    ]


def _metrics(
    g: SupplyGraph,
    node_id: str,
    row: _Row,
    scored: Scored | None,
    st: Structure,
    product_of: dict[str, str],
) -> NodeMetrics:
    node = g.nodes[node_id]
    exp = row.exposure
    drivers = []
    if scored:
        drivers = sorted(
            (
                Driver(feature=k, label=LABELS[k], value=scored.features[k], contribution=c)
                for k, c in scored.contributions.items()
            ),
            key=lambda d: -abs(d.contribution),
        )
    return NodeMetrics(
        node_id=node_id,
        kind=node.kind,
        type=node.type,
        name=node.name,
        industry=node.industry,
        downstream_products=sorted({product_of[o] for o in row.downstream}),
        downstream_orders=len(row.downstream),
        downstream_open_order_value_usd=round(row.downstream_value, 2),
        dominated_products=sorted({product_of[o] for o in row.dominated}),
        dominated_order_ids=sorted(row.dominated),
        dominated_orders=len(row.dominated),
        dominated_value_usd=round(row.dominated_value, 2),
        betweenness=round(st.betweenness.get(node_id, 0.0), 5),
        pagerank_rev=round(st.pagerank_rev.get(node_id, 0.0), 5),
        hhi_inputs=st.hhi_inputs.get(node_id, {}),
        single_sourced_inputs=st.single_sourced_inputs.get(node_id, []),
        sole_source_for=st.sole_source_for.get(node_id, []),
        tts_d=exp.tts_d if exp else None,
        tts_capped=exp.tts_capped if exp else False,
        ttr_d=exp.ttr_d if exp else None,
        ttr_p90_d=exp.ttr_p90_d if exp else None,
        ttr_source=exp.ttr_source if exp else None,
        performance_impact_usd=exp.performance_impact_usd if exp else None,
        risk_score=scored.score if scored else None,
        risk_band=scored.band if scored else None,
        risk_drivers=drivers,
        features=scored.features if scored else {},
        model_version=MODEL_VERSION,
    )


def rank(
    metrics: list[NodeMetrics], metric: str = "dominance", industry: str | None = None
) -> list[NodeMetrics]:
    """The criticality leaderboard: upstream nodes and ports, most critical first."""
    pool = [
        m
        for m in metrics
        if m.type != "customer_site" and (industry is None or m.industry in (industry, None))
    ]

    def gap(m: NodeMetrics) -> float:
        if m.tts_d is None or m.ttr_d is None or m.tts_capped:
            return float("-inf")
        return m.ttr_d - m.tts_d

    keys = {
        "dominance": lambda m: (m.dominated_value_usd, m.dominated_orders),
        "downstream": lambda m: (m.downstream_open_order_value_usd, m.downstream_orders),
        "tts_gap": lambda m: (gap(m), m.performance_impact_usd or 0.0),
        "risk": lambda m: (m.risk_score or 0.0, m.dominated_value_usd),
    }
    if metric not in keys:
        raise ValueError(f"metric must be one of {METRICS}")
    return sorted(pool, key=keys[metric], reverse=True)


def whatif_defaults(g: SupplyGraph, node_id: str) -> DisruptionIn:
    """Pre-filled what-if for a node (C1-AC06): see `defaults_for`."""
    return defaults_for(g.priors, node_id, g.nodes[node_id].type, g.events.get(node_id, []))


def defaults_for(
    priors: Priors, node_id: str, node_type: str, events: list[EventLink]
) -> DisruptionIn:
    """A linked open event's duration and delay, else the node type's TTR as an outage."""
    for e in sorted(events, key=lambda e: -(e.severity * e.confidence)):
        if e.extra_lead_time_d:
            return DisruptionIn(
                node_id=node_id,
                duration_d=max(1.0, e.duration_d or e.extra_lead_time_d),
                capacity_pct=100.0,
                extra_lead_time_d=e.extra_lead_time_d,
            )
        if e.duration_d:
            return DisruptionIn(node_id=node_id, duration_d=max(1.0, e.duration_d))
    p50, _ = priors.ttr(node_type)
    return DisruptionIn(node_id=node_id, duration_d=p50)


def what_if(g: SupplyGraph, req: WhatIfRequest) -> WhatIfResult:
    unknown = [d.node_id for d in req.disruptions if d.node_id not in g.nodes]
    if unknown:
        raise KeyError(f"unknown nodes: {', '.join(unknown)}")
    disruptions = [
        Disruption(
            node=d.node_id,
            duration_d=d.duration_d,
            capacity_pct=d.capacity_pct,
            start_d=d.start_d,
            extra_lead_time_d=d.extra_lead_time_d,
        )
        for d in req.disruptions
    ]
    base = simulate(g, disruptions)
    removed = frozenset(d.node for d in disruptions if d.capacity_pct < 100)
    factor = {d.node: d.capacity_pct / 100 for d in disruptions if 0 < d.capacity_pct < 100}
    tts = ExposureModel(g).tts(removed - set(factor), factor) if removed else None
    result = WhatIfResult(
        disrupted=req.disruptions,
        duration_d=max(d.duration_d for d in req.disruptions),
        capacity_pct=min(d.capacity_pct for d in req.disruptions),
        mc_runs=req.mc_runs,
        seed=req.seed,
        first_impact_d=base.first_impact_d,
        recovery_d=base.recovery_d,
        tts_d=tts,
        orders_late=len(base.late),
        revenue_at_risk_usd=base.revenue_at_risk_usd,
        timeline=base.timeline,
        impacted_orders=[
            OrderImpactOut(
                **{k: v for k, v in i.__dict__.items()},
                facility_name=g.nodes[i.facility].name,
            )
            for i in base.impacts
        ],
        mitigations=mitigations(g, disruptions, base),
        model_version=MODEL_VERSION,
    )
    if req.mc_runs:
        runs = monte_carlo(g, disruptions, req.mc_runs, req.seed)
        horizon = float(g.priors.horizon_d + 60)
        at_risk = [r.revenue_at_risk_usd for r in runs]
        late = [float(len(r.late)) for r in runs]
        recovery = [r.recovery_d if r.recovery_d is not None else horizon for r in runs]
        result.revenue_at_risk_usd_p50, result.revenue_at_risk_usd_p90 = _p50_p90(at_risk)
        result.orders_late_p50, result.orders_late_p90 = _p50_p90(late)
        result.recovery_d_p50, result.recovery_d_p90 = _p50_p90(recovery)
    return result


def _p50_p90(values: list[float]) -> tuple[float, float]:
    deciles = statistics.quantiles(values, n=10, method="inclusive")
    return round(statistics.median(values), 2), round(deciles[8], 2)


def mitigations(
    g: SupplyGraph, disruptions: list[Disruption], outcome: Outcome
) -> list[Mitigation]:
    """Mitigation hints (C1-R03); costed recommendations come with Nexus (M8)."""
    out: list[Mitigation] = []
    for d in disruptions:
        node = g.nodes[d.node]
        if node.kind == "port":
            if node.type == "gateway":
                out.append(
                    Mitigation(
                        action_type="reroute",
                        title="Plan an alternative gateway for urgent export orders",
                        detail=(
                            "Mongla (BDMGL) is the nearest alternative sea gateway; Route Planner "
                            "(C3, M5) prices and times it. Hold orders that miss the slack."
                        ),
                        targets=[i.order_id for i in outcome.late][:10],
                    )
                )
            continue
        for p in sorted(g.makes.get(d.node, set())):
            out_edges = g.outbound.get((d.node, p), [])
            if not out_edges:
                continue
            consumers = {e.dst for e in out_edges}
            volume = sum(g.flow(e) for e in out_edges)
            spare = 0.0
            for f in consumers:
                for alt in g.inbound.get((f, p), []):
                    if alt.src != d.node:
                        spare += max(
                            0.0,
                            g.capacity.get((alt.src, p), 0.0) - g.production.get((alt.src, p), 0.0),
                        )
            if volume > 0 and spare < volume:
                qualified = {alt.src for f in consumers for alt in g.inbound.get((f, p), [])}
                candidates = sorted(
                    n.name
                    for n in g.nodes.values()
                    if n.type == node.type and n.industry == node.industry and n.id not in qualified
                )
                out.append(
                    Mitigation(
                        action_type="dual_source",
                        title=f"Qualify a second source of {g.products[p].name.lower()}",
                        detail=(
                            f"Qualified alternatives cover {spare / volume:.0%} of "
                            f"{node.name}'s volume to {len(consumers)} plants. Same-type "
                            f"candidates to qualify: {', '.join(candidates[:3]) or 'none'}."
                        ),
                        targets=sorted(consumers)[:20],
                    )
                )
    late = outcome.late
    if late:
        worst = max(i.delay_d for i in late)
        out.append(
            Mitigation(
                action_type="increase_safety_stock",
                title=f"Raise input cover by about {worst:.0f} days at the affected plants",
                detail=(
                    f"{len(late)} orders run late by up to {worst:.0f} days; that much extra "
                    "cover of the disrupted inputs would absorb this disruption (estimate)."
                ),
                targets=sorted({i.facility for i in late}),
            )
        )
    return out
