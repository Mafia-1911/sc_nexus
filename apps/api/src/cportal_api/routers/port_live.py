"""/port/live: Chattogram now, from CPA's public TOS dashboard and PCS (DS-PORT-10), for the map.

Real data only. CPA publishes berth codes, not coordinates: vessels at a berth are drawn at the
berth's approximate position (config/ports/bdcgp_berths.yaml, from OSM anchors, A-107); vessels
at the outer anchorage at an illustrative spot among GFW's real anchorage cells (weighted,
stable per vessel). Inbound ships (non-stale ETA) and recent departures are lists, not points.
Yard occupancy, containers lying and the last 24 h come from the latest snapshot holding them.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import yaml
from cportal_core.models import Port, PortCall, PortStateSnapshot, Vessel
from cportal_core.paths import repo_root
from fastapi import APIRouter
from sqlalchemy import select

from cportal_api.deps import SessionDep, meta
from cportal_api.schemas import Envelope

router = APIRouter(tags=["ports"])


def berth_key(code: str) -> str:
    """'GCB07', 'GCB-7', 'CCT/1' → 'GCB7', 'GCB7', 'CCT1' (same rule as the DS-PORT-10 store)."""
    s = re.sub(r"[^A-Z0-9]", "", code.upper())
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", s)


SRC = "DS-PORT-10"
FRESH = timedelta(hours=2)


@cache
def berths() -> dict[str, dict[str, Any]]:
    doc = yaml.safe_load((repo_root() / "config/ports/bdcgp_berths.yaml").read_text())
    return {berth_key(b["code"]): b for b in doc["berths"]}


@cache
def anchorage_cells() -> list[dict[str, Any]]:
    doc = yaml.safe_load((repo_root() / "config/priors/ds_ais_01_synthetic.yaml").read_text())
    return list(doc["anchorage_cells"])


def anchorage_spot(name: str) -> tuple[float, float]:
    """A stable, weighted pick among GFW anchorage cells, with a small spread (illustrative)."""
    cells = anchorage_cells()
    h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    total = sum(c["weight"] for c in cells)
    r = h % total
    for c in cells:
        r -= c["weight"]
        if r < 0:
            break
    dlat = ((h >> 20) % 1000 / 1000 - 0.5) * 0.02
    dlon = ((h >> 40) % 1000 / 1000 - 0.5) * 0.02
    return round(c["lat"] + dlat, 5), round(c["lon"] + dlon, 5)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _latest_part(session: SessionDep, port_id: Any, key: str) -> tuple[Any, datetime | None]:
    row = session.execute(
        select(PortStateSnapshot.yard[key], PortStateSnapshot.ts)
        .where(
            PortStateSnapshot.port_id == port_id,
            PortStateSnapshot.source_id == SRC,
            PortStateSnapshot.yard[key].isnot(None),
            PortStateSnapshot.yard[key].astext != "null",
        )
        .order_by(PortStateSnapshot.ts.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else (None, None)


def classify(pc: PortCall, now: datetime) -> str | None:
    phase = (pc.phase or "").upper()
    attrs = pc.attrs or {}
    if (
        phase not in ("DEPARTED", "COMPLETE")
        and attrs.get("berth")
        and (phase == "WORKING" or pc.berth_start_ts is not None)
    ):
        return "at_berth"  # the TOS at-berth report can be ahead of the PCS phase
    if phase in ("ARRIVED", "ANCHORAGE") or (phase == "WORKING" and not attrs.get("berth")):
        return "at_anchorage"
    if phase == "INBOUND" and not attrs.get("stale"):
        return "expected"
    if (
        phase in ("DEPARTED", "COMPLETE")
        and pc.departure_ts
        and pc.departure_ts > now - timedelta(hours=48)
    ):
        return "departed"
    return None


@router.get("/port/live", response_model=Envelope[dict[str, Any]])
def port_live(session: SessionDep) -> Envelope[dict[str, Any]]:
    port = session.scalar(select(Port).where(Port.locode == "BDCGP"))
    snap = (
        session.scalar(
            select(PortStateSnapshot)
            .where(PortStateSnapshot.port_id == port.id, PortStateSnapshot.source_id == SRC)
            .order_by(PortStateSnapshot.ts.desc())
            .limit(1)
        )
        if port
        else None
    )
    if port is None or snap is None:
        return Envelope(
            data={"available": False, "note": "no CPA poll yet (worker job cpa:fast)"},
            meta=meta([], None, note="no CPA data"),
        )
    now = datetime.now(UTC)
    rows = session.execute(
        select(PortCall, Vessel)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .where(PortCall.source_id == SRC, PortCall.available_at >= snap.ts - timedelta(minutes=30))
    ).all()
    gaz = berths()
    features: list[dict[str, Any]] = []
    expected: list[dict[str, Any]] = []
    departed: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for pc, v in rows:
        status = classify(pc, now)
        if status is None:
            continue
        counts[status] = counts.get(status, 0) + 1
        a = pc.attrs or {}
        item = {
            "name": v.name, "mmsi": v.mmsi, "status": status, "phase": pc.phase,
            "berth": a.get("berth"), "agent": a.get("agent"), "rotation": a.get("rotation"),
            "eta": _iso(pc.arrival_planned_ts), "ata": _iso(pc.arrival_ts),
            "berthed": _iso(pc.berth_start_ts), "etd": _iso(pc.departure_planned_ts),
            "atd": _iso(pc.departure_ts), "cargo": a.get("cargo"),
            "import": a.get("import"), "export": a.get("export"),
        }  # fmt: skip
        if status == "expected":
            expected.append(item)
            continue
        if status == "departed":
            departed.append(item)
            continue
        if status == "at_berth":
            b = gaz.get(berth_key(a["berth"]))
            if b is None:
                unplaced.append(item)
                continue
            lat, lon, how = b["lat"], b["lon"], f"berth {b['code']} (approximate: {b['method']})"
        else:
            lat, lon = anchorage_spot(v.name or str(v.id))
            how = "outer anchorage (illustrative spot; CPA gives no coordinates)"
        features.append({
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {**item, "position": how},
        })  # fmt: skip
    expected.sort(key=lambda x: x["eta"] or "")
    departed.sort(key=lambda x: x["atd"] or "", reverse=True)
    occupied = {
        berth_key(f["properties"]["berth"] or "") for f in features if f["properties"]["berth"]
    }
    berth_points = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
         "properties": {"code": b["code"], "occupied": berth_key(b["code"]) in occupied,
                        "method": b["method"]}}
        for b in gaz.values()
    ]  # fmt: skip
    parts = {
        k: _latest_part(session, port.id, k) for k in ("yards", "lying", "last24", "berth_monthly")
    }
    return Envelope(
        data={
            "available": True,
            "observed_at": snap.ts.isoformat(),
            "fresh": now - snap.ts <= FRESH,
            "counts": counts,
            "queue": snap.queue_by_type,
            "mean_wait_h_24h": snap.mean_wait_h_24h,
            "vessels": {"type": "FeatureCollection", "features": features},
            "berths": {"type": "FeatureCollection", "features": berth_points},
            "expected": expected[:40],
            "departed": departed[:20],
            "unplaced": unplaced,
            **{k: v[0] for k, v in parts.items()},
            "parts_as_of": {k: _iso(v[1]) for k, v in parts.items()},
            "source": "CPA TOS dashboard + PCS (cpatos.gov.bd), public pages",
        },
        meta=meta(
            [snap],
            None,
            as_of=snap.ts,
            note="berth positions approximate; anchorage spots illustrative",
        ),
    )
