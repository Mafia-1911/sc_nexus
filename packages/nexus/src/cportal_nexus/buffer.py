"""Buffer recommendations (C2-R03, C2-AC08, 08 §4) for open disruption alerts, per scenario.

For each alert: the event's nodes (the Chattogram gateway by LOCODE, facilities by link) are
disrupted in C1's cascade for the event's P50 duration at its type's remaining capacity. Plants
whose orders run late get extra safety stock on the inputs that depend on those nodes:

    SS = z·√(L̄·σ_d² + d̄²·σ_L²),  with L̄ and σ_L inflated by the event's delay (P50, P90)

Cost = extra units × unit value × holding rate × carry time. Benefit = confidence × revenue of
the late orders × a lateness penalty rate. Rates and z are estimates, shown as such.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from cportal_c1 import service as c1
from cportal_c1 import store as c1_store
from cportal_c1.graph import SupplyGraph
from cportal_c1.schemas import DisruptionIn, WhatIfRequest
from cportal_core.models import Alert, DisruptionEvent, EventEntityLink, Recommendation, Scenario
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cportal_nexus import BUFFER_VERSION

Z = 1.65  # 95 % cycle service level
DEMAND_CV = 0.2  # daily demand variability (estimate)
HOLDING_RATE = 0.25  # per year, of unit value (estimate)
PENALTY_RATE = (
    0.15  # cost of a late order as a share of its value: discounts, air freight (estimate)
)
MAX_NODES = 8
NS = uuid5(NAMESPACE_URL, "cportal/nexus")
CAPACITY_BY_TYPE = {  # mirrors config/priors/disruptions.yaml for the what-if
    "PORT_OPERATIONS_SUSPENDED": 0, "CYCLONE_STORM": 0, "FIRE_EXPLOSION": 0,
    "LABOR_STRIKE_BLOCKADE": 20, "FLOOD": 50, "PORT_CONGESTION": 60,
}  # fmt: skip


def _nodes(
    session: Session, g: SupplyGraph, event: DisruptionEvent, scenario: Scenario
) -> list[str]:
    nodes = [g.gateway] if g.priors.gateway in (event.locodes or []) else []
    linked = session.scalars(
        select(EventEntityLink.entity_id).where(
            EventEntityLink.event_id == event.id,
            EventEntityLink.entity_type == "facility",
            EventEntityLink.scenario_id == scenario.id,
        )
    ).all()
    plants = [str(f) for f in linked if str(f) in g.nodes]
    # The most depended-on first, so the cap keeps the ones that matter.
    weight = {n: sum(1 for deps in g.order_deps.values() if n in deps) for n in plants}
    return nodes + sorted(plants, key=lambda n: -weight[n])[:MAX_NODES]


def recommend(
    session: Session, g: SupplyGraph, alert: Alert, event: DisruptionEvent, scenario: Scenario
) -> Recommendation | None:
    nodes = _nodes(session, g, event, scenario)
    if not nodes:
        return None
    p50_d = (event.duration_p50_h or 48) / 24
    p90_d = (event.duration_p90_h or p50_d * 24 * 1.6) / 24
    capacity = float(CAPACITY_BY_TYPE.get(event.type, 40))
    result = c1.what_if(
        g,
        WhatIfRequest(
            disruptions=[
                DisruptionIn(node_id=n, duration_d=max(1.0, p50_d), capacity_pct=capacity)
                for n in nodes
            ]
        ),
    )
    late = [o for o in result.impacted_orders if o.late]
    if not late:
        return None
    hit = set(nodes)
    targets: list[dict[str, Any]] = []
    cost = 0.0
    for plant in sorted({o.facility for o in late}):
        for (f, component), need in g.need.items():
            if f != plant or need <= 0 or not hit & g.input_deps(f, component):
                continue
            suppliers = g.inbound.get((f, component), [])
            lead = sum(s.lead_time_d * s.share for s in suppliers) or 14.0
            sd_lead = lead * 0.25
            sd_d = need * DEMAND_CV
            delay = p50_d * (1 - capacity / 100)
            spread = max(0.0, (p90_d - p50_d) / 1.28)
            before = Z * math.sqrt(lead * sd_d**2 + need**2 * sd_lead**2)
            after = Z * math.sqrt((lead + delay) * sd_d**2 + need**2 * (sd_lead**2 + spread**2))
            extra = max(0.0, after - before) + need * delay
            value = g.products[component].unit_value_usd
            carry_d = p90_d + extra / need
            item_cost = extra * value * HOLDING_RATE * carry_d / 365
            cost += item_cost
            targets.append(
                {
                    "facility_id": f,
                    "facility": g.nodes[f].name,
                    "product": component,
                    "units": round(extra, 1),
                    "days_of_cover": round(extra / need, 1),
                    "cost_usd": round(item_cost, 2),
                }
            )
    if not targets:
        return None
    confidence = float(event.confidence or 0.3)
    benefit = confidence * sum(o.revenue_usd for o in late) * PENALTY_RATE
    days = max(t["days_of_cover"] for t in targets)
    return Recommendation(
        id=uuid5(NS, f"buffer:{alert.id}:{scenario.id}"),
        source_id="nexus",
        source_record_id=str(alert.id),
        data_mode="synthetic",
        is_synthetic=True,
        scenario_id=scenario.id,
        generator_version=BUFFER_VERSION,
        alert_id=alert.id,
        action_type="increase_safety_stock",
        target_refs=targets,
        params={
            "days_of_cover_max": days,
            "z": Z,
            "demand_cv": DEMAND_CV,
            "holding_rate": HOLDING_RATE,
            "penalty_rate": PENALTY_RATE,
            "disrupted": nodes,
            "duration_p50_d": round(p50_d, 1),
            "duration_p90_d": round(p90_d, 1),
            "capacity_pct": capacity,
            "orders_late": len(late),
            "revenue_at_risk_usd": round(sum(o.revenue_usd for o in late), 2),
        },
        expected_benefit_usd=round(benefit, 2),
        expected_cost_usd=round(cost, 2),
        confidence=round(confidence, 3),
        rationale=(
            f"{event.title}: a {p50_d:.0f}-day disruption (P90 {p90_d:.0f} d) at "
            f"{len(nodes)} node(s) makes {len(late)} open orders late in this scenario. Up to "
            f"{days:.0f} more days of cover on {len(targets)} inputs absorbs it."
        ),
        evidence_refs=[{"event_id": str(event.id)}],
        status="proposed",
    )


def refresh(session: Session) -> int:
    """Recompute buffer recommendations for every open alert in every scenario. Decisions
    already taken (accepted or dismissed) are kept."""
    alerts = session.execute(
        select(Alert, DisruptionEvent)
        .join(DisruptionEvent, DisruptionEvent.id == Alert.event_id)
        .where(Alert.status.in_(("open", "ack")))
    ).all()
    session.execute(
        delete(Recommendation).where(
            Recommendation.source_id == "nexus", Recommendation.status == "proposed"
        )
    )
    written = 0
    for scenario in session.scalars(select(Scenario)):
        if not alerts:
            break
        g = c1_store.load(session, scenario)
        for alert, event in alerts:
            if alert.scenario_id is not None and alert.scenario_id != scenario.id:
                continue  # a scenario's own alert stays in that scenario
            rec = recommend(session, g, alert, event, scenario)
            if rec is None:
                continue
            decided = session.get(Recommendation, rec.id)
            if decided is not None:
                continue
            session.add(rec)
            written += 1
    return written
