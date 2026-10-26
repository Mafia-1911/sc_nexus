"""/ports and /vessels: port reference, state, calls, daily activity, zones; latest positions.

Real rows (live/replay) are always included; synthetic rows come from the selected scenario.
Forecasts (C4) answer 501 until M6.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from cportal_core.models import (
    AisPositionLatest,
    Location,
    Port,
    PortActivityDaily,
    PortCall,
    PortStateSnapshot,
    PortZone,
    Vessel,
)
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.geo import feature, geojson
from cportal_api.schemas import (
    ActivityOut,
    Envelope,
    FeatureCollection,
    Page,
    PortCallOut,
    PortOut,
    PortStateOut,
    decode_cursor,
    encode_cursor,
)

router = APIRouter(tags=["ports"])
Limit = Annotated[int, Query(ge=1, le=500)]


def _port(session: SessionDep, locode: str) -> Port:
    port = session.scalar(select(Port).where(Port.locode == locode.upper()))
    if port is None:
        raise HTTPException(404, f"unknown port {locode}")
    return port


@router.get("/ports", response_model=Envelope[list[PortOut]])
def list_ports(session: SessionDep) -> Envelope[list[PortOut]]:
    rows = session.execute(
        select(Port, Location.geom)
        .join(Location, Location.id == Port.location_id)
        .order_by(Port.locode)
    ).all()
    out = [
        PortOut(
            id=p.id, locode=p.locode, name=p.name, port_type=p.port_type, tidal=p.tidal,
            max_draught_m=p.max_draught_m, geometry=geojson(geom),
        )
        for p, geom in rows
    ]  # fmt: skip
    return Envelope(data=out, meta=meta([p for p, _ in rows]))


@router.get("/ports/{locode}/state", response_model=Envelope[PortStateOut | None])
def port_state(locode: str, session: SessionDep, scope: ScopeDep) -> Envelope[PortStateOut | None]:
    """The latest snapshot at or before now (queues, berth occupancy, flows, tide)."""
    port = _port(session, locode)
    row = session.scalar(
        select(PortStateSnapshot)
        .where(PortStateSnapshot.port_id == port.id, scope.rows(PortStateSnapshot))
        .order_by(PortStateSnapshot.is_synthetic.desc(), PortStateSnapshot.ts.desc())
        .limit(1)
    )
    data = (
        PortStateOut(
            ts=row.ts, queue_by_type=row.queue_by_type, berth_occupancy=row.berth_occupancy,
            arrivals_24h=row.arrivals_24h, departures_24h=row.departures_24h,
            mean_wait_h_24h=row.mean_wait_h_24h, tide=row.tide,
        )
        if row
        else None
    )  # fmt: skip
    return Envelope(data=data, meta=meta([row] if row else [], scope))


@router.get("/ports/{locode}/calls", response_model=Envelope[Page[PortCallOut]])
def port_calls(
    locode: str,
    session: SessionDep,
    scope: ScopeDep,
    method: Annotated[str | None, Query(description="gfw | cpa_report | sim | …")] = None,
    status: Annotated[str | None, Query(description="active | completed")] = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Envelope[Page[PortCallOut]]:
    port = _port(session, locode)
    q = (
        select(PortCall, Vessel.name)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .where(PortCall.port_id == port.id, scope.rows(PortCall))
    )
    if method:
        q = q.where(PortCall.method == method)
    if status:
        q = q.where(PortCall.status == status)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        q = q.where(
            (PortCall.arrival_ts < datetime.fromisoformat(ts))
            | ((PortCall.arrival_ts == datetime.fromisoformat(ts)) & (PortCall.id < UUID(last_id)))
        )
    rows = session.execute(
        q.order_by(PortCall.arrival_ts.desc().nulls_last(), PortCall.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    items = [
        PortCallOut(
            id=c.id, vessel_id=c.vessel_id, vessel_name=name, status=c.status,
            visit_kind=c.visit_kind, method=c.method, arrival_ts=c.arrival_ts,
            berth_start_ts=c.berth_start_ts, departure_ts=c.departure_ts, waiting_h=c.waiting_h,
            berth_h=c.berth_h, dwell_h=c.dwell_h, quality_flags=c.quality_flags,
            data_mode=c.data_mode, source_id=c.source_id,
        )
        for c, name in page
    ]  # fmt: skip
    nxt = None
    if len(rows) > limit and page[-1][0].arrival_ts is not None:
        nxt = encode_cursor(page[-1][0].arrival_ts, page[-1][0].id)
    return Envelope(
        data=Page(items=items, next_cursor=nxt, limit=limit), meta=meta([c for c, _ in page], scope)
    )


@router.get("/ports/{locode}/activity", response_model=Envelope[list[ActivityOut]])
def port_activity(
    locode: str,
    session: SessionDep,
    scope: ScopeDep,
    days: Annotated[int, Query(ge=1, le=3000)] = 120,
) -> Envelope[list[ActivityOut]]:
    port = _port(session, locode)
    rows = session.scalars(
        select(PortActivityDaily)
        .where(PortActivityDaily.port_id == port.id, scope.rows(PortActivityDaily))
        .order_by(PortActivityDaily.date.desc())
        .limit(days * 2)
    ).all()
    out = [
        ActivityOut(
            date=r.date.isoformat(), calls_total=r.calls_total, calls_by_type=r.calls_by_type,
            import_t=r.import_t, export_t=r.export_t,
        )
        for r in rows
    ]  # fmt: skip
    return Envelope(data=out, meta=meta(rows, scope))


@router.get("/ports/{locode}/zones", response_model=Envelope[FeatureCollection])
def port_zones(locode: str, session: SessionDep) -> Envelope[FeatureCollection]:
    port = _port(session, locode)
    rows = session.scalars(select(PortZone).where(PortZone.port_id == port.id)).all()
    features = [
        feature(z.geom, {"id": str(z.id), "zone_type": z.zone_type, "name": z.name, **z.attrs})
        for z in rows
        if z.geom is not None or z.zone_type == "berth"
    ]
    return Envelope(data=FeatureCollection(features=features), meta=meta(rows))


@router.get("/ports/{locode}/forecast", responses={501: {"description": "C4 arrives in M6"}})
def port_forecast(locode: str) -> None:
    raise HTTPException(501, "Congestion and dwell forecasts arrive with C4 (M6).")


@router.get("/vessels/positions", response_model=Envelope[FeatureCollection])
def vessel_positions(session: SessionDep, scope: ScopeDep) -> Envelope[FeatureCollection]:
    """Latest position per vessel as GeoJSON points (the Control Tower map)."""
    rows = session.execute(
        select(AisPositionLatest, Vessel.name, Vessel.ship_type_group)
        .outerjoin(Vessel, Vessel.id == AisPositionLatest.vessel_id)
        .where(scope.rows(AisPositionLatest))
    ).all()
    features = [
        feature(
            p.geom,
            {
                "mmsi": p.mmsi, "name": name, "type": group, "ts": p.ts.isoformat(),
                "sog_kn": p.sog_kn, "cog_deg": p.cog_deg, "nav_status": p.nav_status,
                "data_mode": p.data_mode,
            },
        )
        for p, name, group in rows
    ]  # fmt: skip
    return Envelope(
        data=FeatureCollection(features=features), meta=meta([p for p, *_ in rows], scope)
    )
