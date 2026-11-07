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
    PortStateSnapshot,
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
from cportal_api.routers import port_live
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


def _cargo_line(attrs: dict[str, Any]) -> tuple[int | None, str | None]:
    imp, exp = attrs.get("import") or {}, attrs.get("export") or {}
    teu_in, teu_out = imp.get("total_teu") or 0, exp.get("total_teu") or 0
    if not (teu_in or teu_out):
        return None, None
    done = imp.get("discharged_teu") or 0
    pct = f" ({done / teu_in:.0%} discharged)" if teu_in else ""
    return (imp.get("total_box") or 0) + (exp.get("total_box") or 0), (
        f"{teu_in:,} TEU import{pct} · {teu_out:,} TEU export"
    )


def _cpa_ships(
    session: SessionDep, port_id: Any, status: list[Status] | None, limit: int, scope: ScopeDep
) -> Envelope[ShipsOut] | None:
    """Real ships from CPA (DS-PORT-10) when a poll is fresh: status from CPA's phase, real
    berthing times and cargo; the dock time of waiting ships from waits learned by polling."""
    snap_ts = session.scalar(
        select(func.max(PortStateSnapshot.ts)).where(
            PortStateSnapshot.port_id == port_id, PortStateSnapshot.source_id == "DS-PORT-10"
        )
    )
    now = datetime.now(UTC)
    if snap_ts is None or now - snap_ts > timedelta(hours=2):
        return None
    waits = sorted(
        w for w in session.scalars(
            select(PortCall.waiting_h).where(
                PortCall.source_id == "DS-PORT-10", PortCall.waiting_h.is_not(None),
                PortCall.berth_start_ts > now - timedelta(days=30),
            )
        ) if w is not None
    )  # fmt: skip
    w50 = waits[len(waits) // 2] if len(waits) >= 5 else None
    w90 = waits[int(len(waits) * 0.9)] if len(waits) >= 5 else None
    rows = session.execute(
        select(PortCall, Vessel)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .where(
            PortCall.source_id == "DS-PORT-10",
            PortCall.available_at >= snap_ts - timedelta(minutes=30),
        )
    ).all()
    mapping = {"at_berth": "at_berth", "at_anchorage": "at_anchorage", "expected": "expected",
               "departed": "departed"}  # fmt: skip
    out: list[ShipOut] = []
    for pc, v in rows:
        st = port_live.classify(pc, now)
        if st is None:
            continue
        a = pc.attrs or {}
        boxes, cargo = _cargo_line(a)
        info = vessel_info.cached(v.mmsi) or vessel_info.cached(v.imo)
        unknown = {"last_port": NO_SOURCE["last_port"]}
        if info is None:
            unknown["insurance"] = NO_SOURCE["insurance"]
        elif info["pi_club"] is None:
            unknown["insurance"] = "P&I insurer not on record (DataDocked)"
        if st == "at_berth":
            dock, dock90, note = pc.berth_start_ts, None, f"berthed at {a.get('berth')} (CPA TOS)"
        elif w50 is not None and w90 is not None:
            start = pc.arrival_ts if st == "at_anchorage" else pc.arrival_planned_ts
            dock = max(now, start + timedelta(hours=w50)) if start else None
            dock90 = max(now, start + timedelta(hours=w90)) if start else None
            note = f"arrival + median wait of {len(waits)} CPA berthings in 30 days"
        else:
            dock, dock90 = None, None
            note = "learning: waits come from watching ships move from anchorage to berth"
        arrival = pc.arrival_ts if st != "expected" else pc.arrival_planned_ts
        out.append(
            ShipOut(
                call_id=str(pc.id), vessel_id=str(v.id), name=v.name, mmsi=v.mmsi, imo=v.imo,
                flag=v.flag_iso3, ship_type=v.ship_type_group or a.get("cargo"),
                loa_m=v.loa_m, gt=v.gt, status=mapping[st],  # type: ignore[arg-type]
                arrival_ts=arrival, berth_ts=pc.berth_start_ts,
                departure_ts=pc.departure_ts or pc.departure_planned_ts,
                hours_in_port=round((now - pc.arrival_ts).total_seconds() / 3600, 1)
                if pc.arrival_ts and st in ("at_berth", "at_anchorage") else None,
                dock_estimate=dock, dock_p90=dock90, dock_note=note,
                containers=boxes, orders=[], cargo_note=cargo,
                unknown=unknown, management=info, data_mode=pc.data_mode,
                is_synthetic=False,
            )
        )  # fmt: skip
    counts = Counter(str(s.status) for s in out)
    if status:
        out = [s for s in out if s.status in status]
    order = {"at_anchorage": 0, "at_berth": 1, "expected": 2, "departed": 3, "in_port": 0}
    out.sort(key=lambda s: (order[s.status], -(s.arrival_ts or now).timestamp()))
    return Envelope(
        data=ShipsOut(observed_at=snap_ts, counts=dict(counts), ships=out[:limit]),
        meta=meta([pc for pc, _ in rows], scope, as_of=snap_ts,
                  note="CPA TOS + PCS (public pages), polled"),
    )  # fmt: skip


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
    if scope.scenario_id is None and scope.horizon == "now":
        cpa = _cpa_ships(session, port.id, status, limit, scope)
        if cpa is not None:  # CPA's own schedule and berth reports, polled (DS-PORT-10)
            return cpa
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
