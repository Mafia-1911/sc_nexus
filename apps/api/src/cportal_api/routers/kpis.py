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
    PortCall,
    PortStateSnapshot,
    Shipment,
    ShipmentOrder,
    SupplyEdge,
)
from fastapi import APIRouter
from sqlalchemy import func, select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.schemas import Envelope, Kpi, KpiStrip

router = APIRouter(tags=["kpis"])
OPEN = ("open", "in_production", "shipped")


@router.get("/kpis", response_model=Envelope[KpiStrip])
def kpis(session: SessionDep, scope: ScopeDep) -> Envelope[KpiStrip]:
    out: list[Kpi] = []

    if scope.scenario_id is None:  # real data at `as_of` (GFW port calls), never synthetic
        out.extend(_cpa_port(session, scope) or _real_port(session, scope))
    else:
        out.extend(_scenario_port(session, scope))
    out.append(_disruptions(session, scope))
    out.append(_orders_at_risk(session, scope))
    out.append(
        Kpi(
            key="co2e_week",
            label="CO2e this week",
            value=None,
            unit="t CO2e",
            detail="per-plan CO2e is in Route Planner; a weekly total needs real shipment volumes",
            meta=meta([], scope, as_of=datetime.now(UTC)),
        )
    )
    return Envelope(data=KpiStrip(kpis=out), meta=meta([], scope, as_of=scope.as_of))


def _cpa_port(session: SessionDep, scope: ScopeDep) -> list[Kpi] | None:
    """When a CPA poll (DS-PORT-10) is fresh: vessels at the outer anchorage as CPA reports them
    (same classification as the map), and the anchorage wait learned from our polls."""
    from cportal_api.routers import port_live  # a sibling router: shared classification

    now = datetime.now(UTC)
    snap = session.scalar(
        select(PortStateSnapshot)
        .where(PortStateSnapshot.source_id == "DS-PORT-10")
        .order_by(PortStateSnapshot.ts.desc())
        .limit(1)
    )
    if snap is None or scope.horizon != "now" or now - snap.ts > timedelta(hours=2):
        return None
    calls = session.scalars(
        select(PortCall).where(
            PortCall.source_id == "DS-PORT-10",
            PortCall.available_at >= snap.ts - timedelta(minutes=30),
        )
    ).all()
    status = [port_live.classify(pc, now) for pc in calls]
    anchored = [pc for pc, st in zip(calls, status, strict=True) if st == "at_anchorage"]
    at_berth = sum(1 for st in status if st == "at_berth")
    waits = sorted(
        w for w in session.scalars(
            select(PortCall.waiting_h).where(
                PortCall.source_id == "DS-PORT-10", PortCall.waiting_h.is_not(None),
                PortCall.berth_start_ts > now - timedelta(days=30),
            )
        ) if w is not None
    )  # fmt: skip
    m = meta(calls, scope, as_of=snap.ts, note="CPA TOS + PCS (public pages), polled")
    learned = len(waits) >= 5
    return [
        Kpi(key="vessels_at_anchorage", label="Vessels at the outer anchorage",
            value=len(anchored), unit="vessels",
            detail=f"{at_berth} at berth · CPA TOS + PCS", meta=m),
        Kpi(key="mean_wait_24h", label="Median wait for a berth (CPA)",
            value=round(waits[len(waits) // 2], 1) if learned else None, unit="h",
            detail=f"{len(waits)} berthings watched in 30 days" if learned
            else "learning: from ships we see move from anchorage to berth", meta=m),
    ]  # fmt: skip


def _real_port(session: SessionDep, scope: ScopeDep) -> list[Kpi]:
    """Vessels in Chattogram's port area and their mean time there, from real GFW port calls at
    the view time. GFW runs days behind: past the latest call, the latest observation stands in
    and the note says so (an estimate for today, no forecast beyond C4's horizon)."""
    t = scope.as_of or datetime.now(UTC)
    real = (
        Port.locode == "BDCGP",
        PortCall.scenario_id.is_(None),
        PortCall.is_synthetic.is_(False),
        PortCall.source_id != "DS-PORT-10",  # GFW visits only; CPA has its own KPIs
    )
    latest = session.scalar(
        select(func.max(PortCall.arrival_ts))
        .join(Port, Port.id == PortCall.port_id)
        .where(*real, PortCall.arrival_ts <= t)
    )
    if latest is None:
        empty = meta([], scope, as_of=t, note="no real port calls before this date")
        return [
            Kpi(key="vessels_at_anchorage", label="Vessels in the port area", value=None,
                unit="vessels", detail="no real port calls before this date", meta=empty),
            Kpi(key="mean_wait_24h", label="Mean time in port, last 24 h", value=None,
                unit="h", detail="no real port calls before this date", meta=empty),
        ]  # fmt: skip
    seen = min(t, latest)
    lag_d = (t - latest).total_seconds() / 86400
    note = None
    if scope.horizon == "future":
        note = f"forecast needs data to {t:%d %b}; latest real call {latest:%d %b} (GFW lag)"
    elif lag_d > 1:
        note = (
            f"observed {latest:%d %b} (GFW runs {lag_d:.0f} days behind); estimated for {t:%d %b}"
        )
    in_port = session.scalars(
        select(PortCall)
        .join(Port, Port.id == PortCall.port_id)
        .where(
            *real,
            PortCall.arrival_ts <= seen,
            PortCall.arrival_ts > seen - timedelta(days=30),
            (PortCall.departure_ts.is_(None)) | (PortCall.departure_ts > seen),
        )
    ).all()
    dwell_h = func.extract("epoch", PortCall.departure_ts - PortCall.arrival_ts) / 3600
    left = session.execute(
        select(func.percentile_cont(0.5).within_group(dwell_h))
        .join(Port, Port.id == PortCall.port_id)
        .where(
            *real,
            PortCall.departure_ts > seen - timedelta(hours=24),
            PortCall.departure_ts <= seen,
            dwell_h <= 30 * 24,  # laid-up ships (months at anchor) are not waiting for a berth
        )
    ).scalar()
    m = meta(in_port, scope, as_of=seen, note=note)
    return [
        Kpi(key="vessels_at_anchorage", label="Vessels in the port area", value=len(in_port),
            unit="vessels", detail=note or f"GFW port visits at {seen:%d %b %H:%M} UTC", meta=m),
        Kpi(key="mean_wait_24h", label="Median time in port, last 24 h",
            value=round(float(left), 1) if left is not None else None, unit="h",
            detail="calls that left in the 24 h before; stays over 30 days excluded",
            meta=m),
    ]  # fmt: skip


def _scenario_port(session: SessionDep, scope: ScopeDep) -> list[Kpi]:
    out: list[Kpi] = []
    # Port state at Chattogram: the scenario's latest snapshot.
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

    return out


def _disruptions(session: SessionDep, scope: ScopeDep) -> Kpi:
    """Active disruptions touching Bangladesh or Chattogram; in real data, those known and
    started by the view time (a forecast day counts events already announced)."""
    q = select(DisruptionEvent).where(
        scope.rows(DisruptionEvent),
        DisruptionEvent.status.in_(("ongoing", "confirmed", "reported")),
        DisruptionEvent.country_iso3.contains(["BGD"])
        | DisruptionEvent.locodes.contains(["BDCGP"]),
    )
    if scope.as_of is not None:
        known = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
        q = q.where(
            (known.is_(None)) | (known <= min(scope.as_of, datetime.now(UTC))),
            (DisruptionEvent.start_est.is_(None)) | (DisruptionEvent.start_est <= scope.as_of),
            (DisruptionEvent.end_est.is_(None))
            | (DisruptionEvent.end_est >= scope.as_of - timedelta(days=1)),
        )
    events = session.scalars(q).all()
    return Kpi(
        key="active_disruptions",
        label="Active disruptions (Bangladesh)",
        value=len(events),
        unit="events",
        meta=meta(events, scope),
    )


def _orders_at_risk(session: SessionDep, scope: ScopeDep) -> Kpi:
    if scope.scenario_id is None:  # no real order book is loaded (orders are the client's)
        return Kpi(key="orders_at_risk", label="Orders at risk (next 30 days)", value=None,
                   unit="orders", detail="no real order book loaded; pick a scenario to see one",
                   meta=meta([], scope, as_of=scope.as_of))  # fmt: skip
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
    return Kpi(
        key="orders_at_risk",
        label="Orders at risk (next 30 days)",
        value=len(at_risk),
        unit="orders",
        detail=f"US$ {revenue:,.0f} revenue; rule-based (late plan or disrupted supplier)",
        meta=meta(at_risk, scope),
    )
