"""/kpis: the Control Tower strip (05 §4: K-01, K-03, K-05, K-07).

M2 serves what the data supports today and says so: observed port state instead of the C4
forecast, a rule-based orders-at-risk count instead of the Nexus P90 test, and CO2e as
unavailable until C3. Each KPI carries its own meta (mode, sources, as_of).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cportal_core.models import (
    CustomerOrder,
    DisruptionEvent,
    EventEntityLink,
    Port,
    PortStateSnapshot,
    Shipment,
    ShipmentOrder,
    SupplyEdge,
)
from fastapi import APIRouter
from sqlalchemy import select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.schemas import Envelope, Kpi, KpiStrip

router = APIRouter(tags=["kpis"])
OPEN = ("open", "in_production", "shipped")


@router.get("/kpis", response_model=Envelope[KpiStrip])
def kpis(session: SessionDep, scope: ScopeDep) -> Envelope[KpiStrip]:
    out: list[Kpi] = []

    # Port state at Chattogram: the latest snapshot in scope (scenario first, else real CPA).
    port = session.scalar(select(Port).where(Port.locode == "BDCGP"))
    snap = None
    if port is not None:
        snap = session.scalar(
            select(PortStateSnapshot)
            .where(PortStateSnapshot.port_id == port.id, scope.rows(PortStateSnapshot))
            .order_by(PortStateSnapshot.is_synthetic.desc(), PortStateSnapshot.ts.desc())
            .limit(1)
        )
    queue = (snap.queue_by_type if snap else {}) or {}
    waiting = sum((queue.get("waiting_for_berth") or {}).values())
    at_anchor = waiting + sum((queue.get("lighterage_or_lighter") or {}).values())
    snap_meta = meta([snap] if snap else [], scope, as_of=snap.ts if snap else None)
    out.append(
        Kpi(
            key="vessels_at_anchorage",
            label="Vessels at the outer anchorage",
            value=at_anchor if snap else None,
            unit="vessels",
            detail=f"{waiting} waiting for a berth" if snap else "no port state in scope",
            meta=snap_meta,
        )
    )
    out.append(
        Kpi(
            key="mean_wait_24h",
            label="Mean wait for a berth, last 24 h",
            value=snap.mean_wait_h_24h if snap else None,
            unit="h",
            detail="observed; P50 forecast arrives with C4 (M6)",
            meta=snap_meta,
        )
    )

    # Active disruptions touching Bangladesh or Chattogram.
    events = session.scalars(
        select(DisruptionEvent).where(
            scope.rows(DisruptionEvent),
            DisruptionEvent.status.in_(("ongoing", "confirmed", "reported")),
            DisruptionEvent.country_iso3.contains(["BGD"])
            | DisruptionEvent.locodes.contains(["BDCGP"]),
        )
    ).all()
    out.append(
        Kpi(
            key="active_disruptions",
            label="Active disruptions (Bangladesh)",
            value=len(events),
            unit="events",
            meta=meta(events, scope),
        )
    )

    # Orders at risk (K-05), rule-based for M2: open orders due within 30 days whose shipment is
    # planned to arrive after the due date, or whose factory buys from a facility linked to an
    # active disruption.
    today = date.today()
    orders = session.scalars(
        select(CustomerOrder).where(
            scope.rows(CustomerOrder),
            CustomerOrder.status.in_(OPEN),
            CustomerOrder.due_date <= today + timedelta(days=30),
        )
    ).all()
    disrupted = set(
        session.scalars(
            select(EventEntityLink.entity_id)
            .join(DisruptionEvent, DisruptionEvent.id == EventEntityLink.event_id)
            .where(
                EventEntityLink.entity_type == "facility",
                DisruptionEvent.status.in_(("ongoing", "confirmed")),
                scope.rows(EventEntityLink),
            )
        )
    )
    exposed = set(
        session.scalars(
            select(SupplyEdge.to_facility_id).where(
                SupplyEdge.from_facility_id.in_(disrupted), scope.rows(SupplyEdge)
            )
        )
    ) if disrupted else set()  # fmt: skip
    late = set(
        session.scalars(
            select(ShipmentOrder.order_id)
            .join(Shipment, Shipment.id == ShipmentOrder.shipment_id)
            .join(CustomerOrder, CustomerOrder.id == ShipmentOrder.order_id)
            .where(
                scope.rows(Shipment),
                Shipment.planned_eta.is_not(None),
                Shipment.planned_eta > CustomerOrder.due_date + timedelta(days=1),
            )
        )
    )
    at_risk = [o for o in orders if o.id in late or o.facility_id in exposed]
    revenue = sum(o.revenue_usd or 0 for o in at_risk)
    out.append(
        Kpi(
            key="orders_at_risk",
            label="Orders at risk (next 30 days)",
            value=len(at_risk),
            unit="orders",
            detail=f"US$ {revenue:,.0f} revenue; rule-based until Nexus (M8)",
            meta=meta(at_risk, scope),
        )
    )
    out.append(
        Kpi(
            key="co2e_week",
            label="CO2e this week",
            value=None,
            unit="t CO2e",
            detail="arrives with C3 routing (M5)",
            meta=meta([], scope, as_of=datetime.now(UTC)),
        )
    )
    return Envelope(data=KpiStrip(kpis=out), meta=meta([snap] if snap else [], scope))
