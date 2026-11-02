"""/ships: ships at and around Chattogram for the Control Tower, at the view time.

Real data: GFW port visits known by `as_of` (real vessel names), at the latest observation when
GFW lags; GFW does not split anchorage from berth, so a ship is "in port" and its dock time is
not observable yet. Scenario: the simulated port (fictional "SYN" vessels, A-012) at the
scenario's start, with simulated berth times and the synthetic cargo linked to each vessel.
Fields with no open source today (last port, destination, insurance) say so instead of guessing.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from cportal_core.models import (
    CustomerOrder,
    Port,
    PortCall,
    Scenario,
    Shipment,
    ShipmentLeg,
    ShipmentOrder,
    Vessel,
)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from cportal_api import vessel_info
from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.schemas import Envelope

router = APIRouter(tags=["ships"])
Status = Literal["expected", "at_anchorage", "in_port", "at_berth", "departed"]
NO_SOURCE = {
    "last_port": "previous port: GFW port events per ship (to wire)",
    "destination": "AIS destination: aisstream global feed (to wire)",
    "insurance": "P&I insurer: look it up (DataDocked, 3 trial credits)",
}


class ShipOut(BaseModel):
    call_id: str
    vessel_id: str
    name: str | None
    mmsi: int | None
    imo: str | None
    flag: str | None
    ship_type: str | None
    loa_m: float | None
    gt: float | None
    status: Status
    arrival_ts: datetime | None
    berth_ts: datetime | None
    departure_ts: datetime | None
    hours_in_port: float | None
    dock_estimate: datetime | None = Field(
        default=None, description="Berth time: simulated in a scenario; not observable in GFW"
    )
    dock_p90: datetime | None = None
    dock_note: str | None = None
    containers: int | None = None
    orders: list[str] = Field(default_factory=list)
    cargo_note: str | None = None
    unknown: dict[str, str] = Field(default_factory=dict, description="Fields with no source yet")
    management: dict[str, Any] | None = Field(
        default=None, description="Owner, manager, class, P&I (DS-VSL-01), when looked up"
    )
    data_mode: str
    is_synthetic: bool


class ShipsOut(BaseModel):
    observed_at: datetime | None
    counts: dict[str, int]
    ships: list[ShipOut]


def _status(pc: PortCall, t: datetime, unsplit: bool) -> Status | None:
    if pc.arrival_ts is None:
        return None
    if pc.arrival_ts > t:
        return "expected"
    if pc.departure_ts is not None and pc.departure_ts <= t:
        return "departed" if pc.departure_ts > t - timedelta(hours=48) else None
    if pc.berth_start_ts is not None and pc.berth_start_ts <= t:
        return "at_berth"
    return "in_port" if unsplit else "at_anchorage"


def _cargo(
    session: SessionDep, scope: ScopeDep, ids: list[Any]
) -> dict[Any, tuple[int, list[str]]]:
    """Containers and order references on synthetic shipments linked to these vessels."""
    if scope.scenario_id is None or not ids:
        return {}
    rows = session.execute(
        select(ShipmentLeg.vessel_id, Shipment.containers, CustomerOrder.reference)
        .join(Shipment, Shipment.id == ShipmentLeg.shipment_id)
        .outerjoin(ShipmentOrder, ShipmentOrder.shipment_id == Shipment.id)
        .outerjoin(CustomerOrder, CustomerOrder.id == ShipmentOrder.order_id)
        .where(ShipmentLeg.vessel_id.in_(ids), ShipmentLeg.scenario_id == scope.scenario_id)
    ).all()
    out: dict[Any, tuple[int, list[str]]] = {}
    for vid, boxes, ref in rows:
        n, refs = out.get(vid, (0, []))
        if ref and ref not in refs:
            refs.append(ref)
        out[vid] = (max(n, len(boxes or [])), refs)
    return out


@router.get("/ships", response_model=Envelope[ShipsOut])
def ships(
    session: SessionDep,
    scope: ScopeDep,
    status: list[Status] | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=60, ge=1, le=300),
) -> Envelope[ShipsOut]:
    port = session.scalar(select(Port).where(Port.locode == "BDCGP"))
    if port is None:
        return Envelope(data=ShipsOut(observed_at=None, counts={}, ships=[]), meta=meta([], scope))
    if scope.scenario_id is None:
        t = scope.as_of or datetime.now(UTC)
        base = (PortCall.port_id == port.id, PortCall.is_synthetic.is_(False))
        latest = session.scalar(
            select(func.max(PortCall.arrival_ts)).where(*base, PortCall.arrival_ts <= t)
        )
        seen = min(t, latest) if latest else t
        # A history view shows what happened that day (GFW rows are dated by download).
        where: tuple[Any, ...] = base
        unsplit, dock_note = True, "GFW does not split anchorage and berth: not observable yet"
        cargo_note = "manifests are private; container counts need the carrier or the client"
    else:
        sc = session.get(Scenario, scope.scenario_id)
        start = str((sc.definition or {}).get("start") if sc else "") or "2026-10-26"
        seen = datetime.fromisoformat(start).replace(tzinfo=UTC)
        where = (PortCall.port_id == port.id, PortCall.scenario_id == scope.scenario_id)
        unsplit, dock_note = False, "baseline: arrival + median berth wait of the last 30 days"
        cargo_note = None
    rows = session.execute(
        select(PortCall, Vessel)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .where(
            *where,
            PortCall.arrival_ts > seen - timedelta(days=30),
            PortCall.arrival_ts <= seen + timedelta(days=3),
            or_(
                PortCall.departure_ts.is_(None), PortCall.departure_ts > seen - timedelta(hours=48)
            ),
        )
        .order_by(PortCall.arrival_ts.desc())
    ).all()
    cargo = _cargo(session, scope, [v.id for _, v in rows])
    waits = sorted(
        (pc.berth_start_ts - pc.arrival_ts).total_seconds() / 3600
        for pc, _ in rows
        if pc.berth_start_ts
        and pc.arrival_ts
        and seen - timedelta(days=30) <= pc.berth_start_ts <= seen
    )
    w50 = waits[len(waits) // 2] if waits else None
    w90 = waits[int(len(waits) * 0.9)] if waits else None
    # The simulator writes an observed row and a truth row per call; the berth time is on one.
    berth = {}
    if not unsplit:
        for pc, v in rows:
            if pc.berth_start_ts is not None and pc.arrival_ts is not None:
                berth[(v.id, pc.arrival_ts.replace(microsecond=0))] = pc.berth_start_ts
    out: list[ShipOut] = []
    seen_vessels: set[Any] = set()
    for pc, v in rows:
        st = _status(pc, seen, unsplit)
        if st is None or v.id in seen_vessels or (st == "expected" and scope.scenario_id is None):
            continue
        seen_vessels.add(v.id)
        key = (v.id, pc.arrival_ts.replace(microsecond=0)) if pc.arrival_ts else None
        dock = None if unsplit else (pc.berth_start_ts or (berth.get(key) if key else None))
        dock90 = dock
        if dock is None and not unsplit and pc.arrival_ts and w50 is not None and w90 is not None:
            dock = max(seen, pc.arrival_ts + timedelta(hours=w50))
            dock90 = max(seen, pc.arrival_ts + timedelta(hours=w90))
        boxes, refs = cargo.get(v.id, (None, []))
        info = (
            None if pc.is_synthetic else (vessel_info.cached(v.mmsi) or vessel_info.cached(v.imo))
        )
        unknown = dict(NO_SOURCE)
        if info is not None:
            unknown.pop("insurance")
            if info["pi_club"] is None:
                unknown["insurance"] = "P&I insurer not on record (DataDocked)"
        out.append(
            ShipOut(
                call_id=str(pc.id), vessel_id=str(v.id), name=v.name, mmsi=v.mmsi, imo=v.imo,
                flag=v.flag_iso3, ship_type=v.ship_type_group, loa_m=v.loa_m, gt=v.gt,
                status=st, arrival_ts=pc.arrival_ts, berth_ts=pc.berth_start_ts,
                departure_ts=pc.departure_ts,
                hours_in_port=round((seen - pc.arrival_ts).total_seconds() / 3600, 1)
                if pc.arrival_ts and pc.arrival_ts <= seen and st != "departed" else None,
                dock_estimate=dock,
                dock_p90=dock90 if st != "departed" else None,
                dock_note=dock_note, containers=boxes, orders=refs,
                cargo_note=cargo_note if boxes is None else None,
                unknown=unknown, management=info, data_mode=pc.data_mode,
                is_synthetic=pc.is_synthetic,
            )
        )  # fmt: skip
    counts = Counter(str(s.status) for s in out)
    if status:
        out = [s for s in out if s.status in status]
    order = {"at_anchorage": 0, "in_port": 0, "at_berth": 1, "expected": 2, "departed": 3}
    # Newest first within each status: the ships that just arrived or just left lead.
    out.sort(key=lambda s: (order[s.status], -(s.departure_ts or s.arrival_ts or seen).timestamp()))
    rows_meta = [pc for pc, _ in rows]
    return Envelope(
        data=ShipsOut(observed_at=seen, counts=dict(counts), ships=out[:limit]),
        meta=meta(rows_meta, scope, as_of=seen),
    )


@router.post("/ships/{mmsi}/management", response_model=Envelope[dict[str, Any]])
def look_up_management(mmsi: int, session: SessionDep) -> Envelope[dict[str, Any]]:
    """Owner, manager, class society and P&I insurer of a real ship (DataDocked, on demand:
    3 trial credits each, at most a few a day; cached for a year)."""
    vessel = session.scalar(select(Vessel).where(Vessel.mmsi == mmsi))
    if vessel is None:
        raise HTTPException(404, "unknown ship")
    if str(mmsi).startswith("999"):
        raise HTTPException(400, "synthetic vessel: no real registry entry")
    try:
        info = vessel_info.lookup(str(mmsi))
    except vessel_info.LookupError_ as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return Envelope(data=info, meta=meta([], None, note="DS-VSL-01 DataDocked (trial)"))
