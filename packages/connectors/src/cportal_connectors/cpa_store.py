"""DS-PORT-10 into the database: CPA visits as port calls, a port-state snapshot per poll.

Real data (`is_synthetic` false, `data_mode` live). Vessels are matched by normalised name to
real vessels already known (GFW names, so a CPA visit can carry an MMSI), else created by name.
PCS times are agents' declarations: an INBOUND visit whose ETA is more than `STALE_D` days old
is flagged stale (not shown as expected). The at-berth reports add the berthed-on time, ETD and
cargo progress; the anchorage wait = berthed-on minus ATA when both exist.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cportal_core.models import Port, PortCall, PortStateSnapshot, PortZone, Vessel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cportal_connectors.cpa_tos import Fetched, berth_key, vessel_key

NS = uuid5(NAMESPACE_URL, "cportal/DS-PORT-10")
SRC = "DS-PORT-10"
STALE_D = 3
RECENT_BREAKBULK_D = 15
DONE = ("DEPARTED", "COMPLETE")


def _lineage(record_id: str, now: datetime) -> dict[str, Any]:
    return {
        "source_id": SRC,
        "source_record_id": record_id[:256],
        "data_mode": "live",
        "is_synthetic": False,
        "available_at": now,
    }


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    return None if a is None or b is None or b < a else round((b - a).total_seconds() / 3600, 2)


def store(session: Session, results: list[Fetched], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    port = session.scalar(select(Port).where(Port.locode == "BDCGP"))
    if port is None:
        raise RuntimeError("port BDCGP missing: run the reference ingest first")
    got = {f.page: f.parsed for f in results if f.parsed is not None}
    pcs: list[dict[str, Any]] = got.get("pcs", [])
    berthed: dict[str, tuple[dict[str, Any], str]] = {}
    for kind in ("container", "breakbulk"):
        for r in got.get(f"at_berth_{kind}", []):
            berthed[vessel_key(r["vessel"])] = (r, kind)
    known: dict[str, Vessel] = {}
    for v in session.scalars(
        select(Vessel).where(Vessel.is_synthetic.is_(False), Vessel.name.is_not(None))
    ):
        k = vessel_key(v.name or "")
        if k and (k not in known or (v.mmsi and not known[k].mmsi)):
            known[k] = v
    zones = {
        berth_key(z.name): z.id
        for z in session.scalars(select(PortZone).where(PortZone.port_id == port.id))
    }

    def vessel(name: str) -> Vessel:
        k = vessel_key(name)
        if k in known:
            return known[k]
        v = Vessel(
            id=uuid5(NS, f"vessel:{k}"), name=name.strip()[:120], **_lineage(f"vessel:{k}", now)
        )
        session.merge(v)
        known[k] = v
        return v

    prior = {
        pid: attrs
        for pid, attrs in session.execute(
            select(PortCall.id, PortCall.attrs).where(PortCall.source_id == SRC)
        )
    }
    calls = 0
    seen_keys: set[str] = set()
    for visit in pcs:
        k = vessel_key(visit["vessel"])
        seen_keys.add(k)
        found = berthed.get(k)
        br: dict[str, Any] | None = found[0] if found else None
        cargo_kind: str | None = found[1] if found else None
        phase = visit["phase"]
        # The TOS at-berth report is fresher than the PCS phase (a ship PCS still calls ARRIVED
        # can already be alongside): its berthed-on time counts for ARRIVED visits too.
        berth_on = (
            br["berthed_on"]
            if br
            and br["berth"]
            and phase in ("ARRIVED", "WORKING", *DONE)
            and br["berthed_on"]
            and br["berthed_on"] <= now
            else None
        )
        if (
            berth_on
            and visit["atd"]
            and not (visit["atd"] - timedelta(days=30) <= berth_on <= visit["atd"])
        ):
            berth_on = None  # an at-berth row from an earlier visit of the same ship
        cid = uuid5(NS, f"visit:{visit['visit_ref']}")
        # PCS shows the current phase only: the first time each phase is seen builds the history
        # (anchorage wait = first seen WORKING minus first seen ARRIVED, from our own polls).
        first = dict((prior.get(cid) or {}).get("first_seen") or {})
        first.setdefault(phase, now.isoformat())
        # A wait is learned only if we saw the ship waiting (ARRIVED, no berth yet) before we saw
        # it alongside; a ship already berthed at our first look tells nothing about its wait.
        if phase == "ARRIVED" and visit["ata"] and berth_on is None:
            first.setdefault("ANCHORED_ATA", visit["ata"].isoformat())
            first.setdefault("ANCHORED_SEEN", now.isoformat())
        anchored = (
            datetime.fromisoformat(first["ANCHORED_ATA"]) if "ANCHORED_ATA" in first else None
        )
        seen_waiting = datetime.fromisoformat(first["ANCHORED_SEEN"]) if anchored else None
        waited = (
            _hours(anchored, berth_on)
            if anchored and berth_on and seen_waiting and berth_on > seen_waiting
            else None
        )
        code = visit["berth"] or (br["berth"] if br else None)
        arrival, quality = visit["ata"], []
        if berth_on and arrival and berth_on < arrival:  # CPA: berthed before its declared ATA
            arrival = berth_on
            quality.append("ATA after berthing in CPA data; arrival taken as the berthing time")
        stale = (
            phase == "INBOUND"
            and visit["eta"] is not None
            and visit["eta"] < now - timedelta(days=STALE_D)
        )
        session.merge(
            PortCall(
                id=cid,
                vessel_id=vessel(visit["vessel"]).id,
                port_id=port.id,
                status="completed" if phase in DONE or visit["atd"] else "active",
                arrival_ts=arrival,
                anchorage_start_ts=None if quality else (anchored or visit["ata"]),
                anchorage_end_ts=None if quality else berth_on,
                berth_start_ts=berth_on,
                departure_ts=visit["atd"],
                departure_planned_ts=visit["etd"] or (br["etd"] if br else None),
                arrival_planned_ts=visit["eta"],
                phase=phase,
                waiting_h=waited,
                berth_h=_hours(berth_on, visit["atd"]),
                dwell_h=_hours(arrival, visit["atd"]),
                berth_zone_id=zones.get(berth_key(code)) if code else None,
                method="cpa_report",
                attrs={
                    "visit_ref": visit["visit_ref"],
                    "rotation": visit["rotation"],
                    "agent": visit["agent"],
                    "operator": visit["operator"],
                    "berth": code,
                    "cargo": cargo_kind,
                    "stale": stale,
                    "first_seen": first,
                    "quality": quality,
                    "import": br["import"] if br else None,
                    "export": br["export"] if br else None,
                    "occupation": br["occupation"] if br else None,
                },
                **_lineage(f"visit:{visit['visit_ref']}", now),
            )
        )
        calls += 1
    # Break-bulk vessels on the TOS report but not (yet) in PCS: recent ones only (the report
    # keeps months-old rows), mostly lightering at the outer anchorage (no berth).
    for k, (br, kind) in berthed.items():
        if k in seen_keys or br["berthed_on"] is None:
            continue
        if br["berthed_on"] < now - timedelta(days=RECENT_BREAKBULK_D) and (
            br["etd"] is None or br["etd"] < now - timedelta(days=1)
        ):
            continue
        rid = f"tos:{k}:{br['berthed_on']:%Y%m%d%H%M}"
        session.merge(
            PortCall(
                id=uuid5(NS, rid),
                vessel_id=vessel(br["vessel"]).id,
                port_id=port.id,
                status="active",
                arrival_ts=br["berthed_on"],
                berth_start_ts=br["berthed_on"] if br["berth"] else None,
                anchorage_start_ts=None if br["berth"] else br["berthed_on"],
                departure_planned_ts=br["etd"],
                phase="WORKING" if br["berth"] else "ANCHORAGE",
                berth_zone_id=zones.get(berth_key(br["berth"])) if br["berth"] else None,
                method="cpa_report",
                attrs={
                    "berth": br["berth"],
                    "cargo": kind,
                    "import": br["import"],
                    "export": br["export"],
                    "occupation": br["occupation"],
                    "stale": False,
                },
                **_lineage(rid, now),
            )
        )
        calls += 1
    snapshot = _snapshot(session, port.id, got, berthed, pcs, now)
    return {"calls": calls, "vessels": len(known), "snapshot": snapshot}


def _snapshot(
    session: Session,
    port_id: UUID,
    got: dict[str, Any],
    berthed: dict[str, tuple[dict[str, Any], str]],
    pcs: list[dict[str, Any]],
    now: datetime,
) -> str:
    live = [
        v
        for v in pcs
        if not (v["phase"] == "INBOUND" and v["eta"] and v["eta"] < now - timedelta(days=STALE_D))
    ]
    phases: dict[str, int] = {}
    for v in live:
        phases[v["phase"].lower()] = phases.get(v["phase"].lower(), 0) + 1
    bb_anchorage = sum(
        1
        for r, kind in berthed.values()
        if kind == "breakbulk"
        and not r["berth"]
        and r["etd"]
        and r["etd"] > now - timedelta(days=1)
    )
    occupancy = {
        r["berth"]: {
            "vessel": r["vessel"],
            "berthed_on": r["berthed_on"].isoformat() if r["berthed_on"] else None,
            "etd": r["etd"].isoformat() if r["etd"] else None,
            "cargo": kind,
            "import": r["import"],
            "export": r["export"],
            "occupation": r["occupation"],
        }
        for r, kind in berthed.values()
        if r["berth"]
    }
    waits = [
        h
        for v in pcs
        for br in [berthed.get(vessel_key(v["vessel"]), (None, None))[0]]
        if br
        and br["berthed_on"]
        and v["ata"]
        and now - timedelta(hours=24) <= br["berthed_on"] <= now
        for h in [_hours(v["ata"], br["berthed_on"])]
        if h is not None
    ]
    sid = uuid5(NS, f"snapshot:{now:%Y%m%dT%H%M}")
    session.merge(
        PortStateSnapshot(
            id=sid,
            port_id=port_id,
            ts=now,
            queue_by_type={**phases, "breakbulk_at_anchorage": bb_anchorage},
            berth_occupancy=occupancy,
            arrivals_24h=sum(
                1 for v in pcs if v["ata"] and now - timedelta(hours=24) <= v["ata"] <= now
            ),
            departures_24h=sum(
                1 for v in pcs if v["atd"] and now - timedelta(hours=24) <= v["atd"] <= now
            ),
            mean_wait_h_24h=round(sum(waits) / len(waits), 1) if waits else None,
            yard={
                "yards": got.get("yard"),
                "lying": got.get("lying"),
                "last24": got.get("last24"),
                "performance24": got.get("performance24"),
                "berth_monthly": got.get("berth_monthly"),
                "pages": sorted(got),
            },
            **_lineage(f"snapshot:{now:%Y%m%dT%H%M}", now),
        )
    )
    return str(sid)
