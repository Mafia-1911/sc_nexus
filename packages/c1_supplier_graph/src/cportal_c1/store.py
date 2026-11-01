"""Database side of C1: load a scenario's graph, fingerprint its inputs, save results.

A scenario's network rows are synthetic and carry its `scenario_id`; disruption events and
their links may also be real (from C2), so those queries take real rows too.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cportal_core.models import (
    Base,
    Batch,
    BomEdge,
    CustomerOrder,
    DisruptionEvent,
    EventEntityLink,
    Facility,
    GraphMetric,
    InventoryPosition,
    Location,
    Organization,
    Product,
    Scenario,
    SupplyEdge,
    WhatIfResult,
)
from sqlalchemy import ColumnElement, any_, delete, false, func, literal, or_, select
from sqlalchemy.orm import Session

from cportal_c1 import MODEL_VERSION
from cportal_c1.graph import (
    OPEN_EVENT,
    EventLink,
    GraphBuilder,
    SupplyGraph,
    assemble,
    event_link,
    port_node,
)
from cportal_c1.priors import Priors, load_priors
from cportal_c1.schemas import NodeMetrics
from cportal_c1.schemas import WhatIfResult as WhatIfOut

SOURCE = "c1"
INPUT_TABLES: tuple[type[Base], ...] = (
    Facility,
    SupplyEdge,
    BomEdge,
    CustomerOrder,
    InventoryPosition,
    Batch,
    DisruptionEvent,
    EventEntityLink,
)


def scenario_row(session: Session, key: str) -> Scenario | None:
    return session.scalar(select(Scenario).where(Scenario.key == key))


def _scoped(model: Any, scenario_id: UUID) -> ColumnElement[bool]:
    return model.scenario_id == scenario_id


def _with_real(model: Any, scenario_id: UUID) -> ColumnElement[bool]:
    return or_(model.scenario_id == scenario_id, model.is_synthetic == false())


def load(session: Session, scenario: Scenario, priors: Priors | None = None) -> SupplyGraph:
    priors = priors or load_priors()
    sid = scenario.id
    as_of = scenario.available_at or datetime.now(UTC)
    b = GraphBuilder(priors, as_of)
    b.facilities = {
        f.id: f for f in session.scalars(select(Facility).where(_scoped(Facility, sid)))
    }
    b.orgs = {
        o.id: o for o in session.scalars(select(Organization).where(_scoped(Organization, sid)))
    }
    location_ids = [f.location_id for f in b.facilities.values()]
    for loc_id, lon, lat, country in session.execute(
        select(
            Location.id, func.ST_X(Location.geom), func.ST_Y(Location.geom), Location.country_iso2
        ).where(Location.id.in_(location_ids))
    ):
        if lon is not None and lat is not None:
            b.points[loc_id] = (float(lon), float(lat), country)
    b.products = {p.id: p for p in session.scalars(select(Product).where(_scoped(Product, sid)))}
    edges = list(session.scalars(select(SupplyEdge).where(_scoped(SupplyEdge, sid))))
    bom = [
        (
            b.products[e.parent_product_id].sku,
            b.products[e.component_product_id].sku,
            e.qty_per_unit,
        )
        for e in session.scalars(select(BomEdge).where(_scoped(BomEdge, sid)))
        if e.parent_product_id in b.products and e.component_product_id in b.products
    ]
    orders = [
        (
            str(o.id),
            o.reference,
            o.facility_id,
            o.product_id,
            o.qty,
            o.due_date,
            o.revenue_usd,
            o.buyer_org_id,
            o.status,
        )
        for o in session.scalars(select(CustomerOrder).where(_scoped(CustomerOrder, sid)))
    ]
    stock = [
        (s.facility_id, s.product_id, s.ts, s.on_hand)
        for s in session.scalars(select(InventoryPosition).where(_scoped(InventoryPosition, sid)))
    ]
    # Incoming lots count against their supplier; finished-goods lots (C5) against the plant
    # that made them (C5-R04), where only an AQL rejection is bad (pharma QA holds are routine).
    lots = [
        (supplier, lot_status, produced)
        if supplier is not None
        else (plant, "rejected" if lot_status == "rejected" else "released", produced)
        for supplier, plant, lot_status, produced in session.execute(
            select(
                Batch.supplier_facility_id, Batch.facility_id, Batch.status, Batch.produced_at
            ).where(_scoped(Batch, sid), Batch.status != "in_process")
        )
    ]
    events = {
        e.id: e
        for e in session.scalars(
            select(DisruptionEvent).where(
                _with_real(DisruptionEvent, sid), DisruptionEvent.status.in_(OPEN_EVENT)
            )
        )
    }
    links = [
        (link.entity_type, link.entity_id, events[link.event_id], link.impact_hint)
        for link in session.scalars(select(EventEntityLink).where(_with_real(EventEntityLink, sid)))
        if link.event_id in events
    ]
    return assemble(
        b,
        edges=edges,
        bom=bom,
        orders=orders,
        stock=stock,
        lots=lots,
        links=links,
        port_events=[e for e in events.values() if e.locodes],
    )


def fingerprint(session: Session, scenario: Scenario, priors: Priors | None = None) -> str:
    """Changes when any input row of the scenario (or a real event) changes, or the priors."""
    priors = priors or load_priors()
    parts: list[Any] = [MODEL_VERSION, json.dumps(priors.raw, sort_keys=True, default=str)]
    for model in INPUT_TABLES:
        where = (
            _with_real(model, scenario.id)
            if model in (DisruptionEvent, EventEntityLink)
            else _scoped(model, scenario.id)
        )
        count, newest = session.execute(
            select(func.count(), func.max(model.updated_at)).where(where)  # type: ignore[attr-defined]
        ).one()
        parts.append((model.__tablename__, count, str(newest)))
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:32]


def stored_fingerprint(session: Session, scenario: Scenario) -> str | None:
    return session.scalar(
        select(GraphMetric.inputs_fingerprint)
        .where(GraphMetric.scenario_id == scenario.id)
        .limit(1)
    )


def _lineage(scenario: Scenario, as_of: datetime) -> dict[str, Any]:
    """C1 outputs describe a scenario's (synthetic) world, so they are synthetic too."""
    return {
        "source_id": SOURCE,
        "data_mode": "synthetic",
        "is_synthetic": True,
        "scenario_id": scenario.id,
        "generator_version": MODEL_VERSION,
        "available_at": as_of,
    }


def save_metrics(
    session: Session,
    scenario: Scenario,
    metrics: list[NodeMetrics],
    as_of: datetime,
    inputs_fingerprint: str,
) -> int:
    """Replace the scenario's metrics with these."""
    session.execute(delete(GraphMetric).where(GraphMetric.scenario_id == scenario.id))
    lineage = _lineage(scenario, as_of)
    for m in metrics:
        facility_id = UUID(m.node_id) if m.kind == "facility" else None
        session.add(
            GraphMetric(
                **lineage,
                source_record_id=m.node_id,
                node_id=m.node_id,
                node_kind=m.kind,
                node_type=m.type,
                facility_id=facility_id,
                name=m.name,
                industry=m.industry,
                as_of=as_of,
                downstream_products=m.downstream_products,
                downstream_orders=m.downstream_orders,
                downstream_open_order_value_usd=m.downstream_open_order_value_usd,
                dominated_products=m.dominated_products,
                dominated_order_ids=m.dominated_order_ids,
                dominated_orders=m.dominated_orders,
                dominated_value_usd=m.dominated_value_usd,
                betweenness=m.betweenness,
                pagerank_rev=m.pagerank_rev,
                hhi_inputs=m.hhi_inputs,
                single_sourced_inputs=m.single_sourced_inputs,
                sole_source_for=m.sole_source_for,
                tts_d=m.tts_d,
                tts_capped=m.tts_capped,
                ttr_d=m.ttr_d,
                ttr_p90_d=m.ttr_p90_d,
                ttr_source=m.ttr_source,
                performance_impact_usd=m.performance_impact_usd,
                risk_score=m.risk_score,
                risk_band=m.risk_band,
                risk_drivers=[d.model_dump() for d in m.risk_drivers],
                features=m.features,
                model_version=m.model_version,
                inputs_fingerprint=inputs_fingerprint,
            )
        )
    return len(metrics)


def save_whatif(
    session: Session,
    scenario: Scenario,
    result: WhatIfOut,
    as_of: datetime,
    job_id: UUID | None = None,
) -> UUID:
    row = WhatIfResult(
        **_lineage(scenario, as_of),
        disrupted=[d.model_dump() for d in result.disrupted],
        duration_d=result.duration_d,
        capacity_pct=result.capacity_pct,
        mc_runs=result.mc_runs,
        seed=result.seed,
        orders_late=result.orders_late,
        revenue_at_risk_usd=result.revenue_at_risk_usd,
        revenue_at_risk_usd_p50=result.revenue_at_risk_usd_p50,
        revenue_at_risk_usd_p90=result.revenue_at_risk_usd_p90,
        first_impact_d=result.first_impact_d,
        recovery_d=result.recovery_d,
        tts_d=result.tts_d,
        result=result.model_dump(mode="json"),
        model_version=result.model_version,
        job_id=job_id,
    )
    session.add(row)
    session.flush()
    return row.id


def refresh(session: Session, scenario: Scenario, *, force: bool = False) -> int | None:
    """Recompute a scenario's metrics when its inputs changed. Returns rows written, or None
    when they were current."""
    from cportal_c1.service import compute_metrics  # the heavy part, only when needed

    current = fingerprint(session, scenario)
    if not force and stored_fingerprint(session, scenario) == current:
        return None
    graph = load(session, scenario)
    return save_metrics(session, scenario, compute_metrics(graph), graph.as_of, current)


def metrics_from_rows(rows: list[GraphMetric]) -> list[NodeMetrics]:
    """Stored metrics back into the service's shape (for ranking and the API)."""
    return [
        NodeMetrics(
            node_id=r.node_id,
            kind=r.node_kind,
            type=r.node_type,
            name=r.name,
            industry=r.industry,
            downstream_products=list(r.downstream_products),
            downstream_orders=r.downstream_orders,
            downstream_open_order_value_usd=r.downstream_open_order_value_usd,
            dominated_products=list(r.dominated_products),
            dominated_order_ids=list(r.dominated_order_ids),
            dominated_orders=r.dominated_orders,
            dominated_value_usd=r.dominated_value_usd,
            betweenness=r.betweenness,
            pagerank_rev=r.pagerank_rev,
            hhi_inputs=dict(r.hhi_inputs),
            single_sourced_inputs=list(r.single_sourced_inputs),
            sole_source_for=list(r.sole_source_for),
            tts_d=r.tts_d,
            tts_capped=r.tts_capped,
            ttr_d=r.ttr_d,
            ttr_p90_d=r.ttr_p90_d,
            ttr_source=r.ttr_source,
            performance_impact_usd=r.performance_impact_usd,
            risk_score=r.risk_score,
            risk_band=r.risk_band,
            risk_drivers=list(r.risk_drivers),
            features=dict(r.features),
            model_version=r.model_version,
        )
        for r in rows
    ]


def linked_events(session: Session, scenario: Scenario, node_id: str) -> list[EventLink]:
    """Open events linked to one node (a facility by link, the gateway by LOCODE)."""
    priors = load_priors()
    open_events = _with_real(DisruptionEvent, scenario.id)
    if node_id == port_node(priors.gateway):
        rows = session.scalars(
            select(DisruptionEvent).where(
                open_events,
                DisruptionEvent.status.in_(OPEN_EVENT),
                literal(priors.gateway) == any_(DisruptionEvent.locodes),
            )
        )
        return [event_link(e, {}) for e in rows]
    if node_id.startswith("port:"):
        return []
    pairs = session.execute(
        select(DisruptionEvent, EventEntityLink.impact_hint)
        .join(EventEntityLink, EventEntityLink.event_id == DisruptionEvent.id)
        .where(
            open_events,
            DisruptionEvent.status.in_(OPEN_EVENT),
            EventEntityLink.entity_type == "facility",
            EventEntityLink.entity_id == UUID(node_id),
            _with_real(EventEntityLink, scenario.id),
        )
    ).all()
    return [event_link(e, hint) for e, hint in pairs]
