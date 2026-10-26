"""AIS (aisstream), Global Fishing Watch port visits, presence, SAR and vessel identity."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from cportal_core.enums import (
    PortCallFlag,
    PortCallMethod,
    PortCallStatus,
    SatelliteSensor,
    ShipTypeGroup,
    VisitKind,
)
from cportal_core.ids import imo_check_digit_ok, port_id, vessel_id
from cportal_core.schemas.records import (
    AisPositionRecord,
    PortCallRecord,
    PortCallStopRecord,
    Record,
    SatelliteObservationRecord,
    VesselRecord,
    ZonePresenceDailyRecord,
    point,
)

from cportal_connectors.canonical import ParseContext, lagged, parse_ts

# --- aisstream (DS-AIS-01) ---------------------------------------------------------------------

POSITION_TYPES = {
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
}
STATIC_TYPES = {"ShipStaticData", "StaticDataReport"}
_GO_TIME = re.compile(r"^(\S+ \d{2}:\d{2}:\d{2})(?:\.(\d+))? ([+-]\d{4}) UTC$")


def go_time(text: str) -> datetime:
    """aisstream's Go-formatted `time_utc`: '2026-10-25 22:59:34.035581545 +0000 UTC'."""
    match = _GO_TIME.match(text.strip())
    if not match:
        raise ValueError(f"unexpected time_utc: {text!r}")
    base, frac, offset = match.groups()
    micro = (frac or "0")[:6].ljust(6, "0")
    return datetime.strptime(f"{base}.{micro} {offset}", "%Y-%m-%d %H:%M:%S.%f %z").astimezone(UTC)


def ais_ship_type_group(code: int | None) -> ShipTypeGroup | None:
    if code is None or code <= 0:
        return None
    if 70 <= code <= 79:
        return ShipTypeGroup.CARGO
    if 80 <= code <= 89:
        return ShipTypeGroup.TANKER
    if 60 <= code <= 69:
        return ShipTypeGroup.PASSENGER
    if code == 30:
        return ShipTypeGroup.FISHING
    if code in (31, 32, 52) or 50 <= code <= 59:
        return ShipTypeGroup.TUG_SERVICE
    return ShipTypeGroup.OTHER


def _none_if(value: Any, *sentinels: float) -> float | None:
    """SC-08: AIS 'not available' sentinels become null."""
    if value is None:
        return None
    number = float(value)
    return None if any(abs(number - s) < 1e-9 for s in sentinels) else number


def _eta(eta: dict[str, Any] | None, ref: datetime) -> datetime | None:
    """AIS ETA has month/day/hour/minute but no year: take the next occurrence after `ref`."""
    if not eta or not eta.get("Month") or not eta.get("Day"):
        return None
    hour = eta.get("Hour", 24)
    minute = eta.get("Minute", 60)
    if hour >= 24 or minute >= 60:
        hour, minute = 0, 0
    for year in (ref.year, ref.year + 1):
        try:
            ts = datetime(year, eta["Month"], eta["Day"], hour, minute, tzinfo=UTC)
        except ValueError:
            return None
        if ts >= ref - timedelta(days=1):
            return ts
    return None


def parse_aisstream_jsonl(body: bytes, ctx: ParseContext) -> list[Record]:
    """Collector/twin envelopes `{received_at, frame[, is_synthetic, scenario_id]}`, one per line.

    Vessel rows follow the brief's rule: keyed by IMO when a static message gives a valid one,
    else by MMSI. Every position points at a vessel row this batch also emits.
    """
    frames: list[tuple[dict[str, Any], datetime | None]] = []
    for line in body.decode("utf-8").splitlines():
        if not line.strip():
            continue
        envelope = json.loads(line)
        if envelope.get("is_synthetic") and not ctx.is_synthetic:
            raise ValueError("synthetic AIS frame in a non-synthetic parse (AGENTS.md rule 3)")
        frames.append((json.loads(envelope["frame"]), parse_ts(envelope.get("received_at"))))

    vessels: dict[int, VesselRecord] = {}
    for frame, received in frames:  # statics first, so positions find the IMO key
        kind = frame.get("MessageType")
        if kind not in STATIC_TYPES:
            continue
        meta = frame.get("MetaData") or {}
        mmsi = int(meta.get("MMSI") or 0)
        if not 100_000_000 <= mmsi <= 999_999_999:
            continue
        msg = (frame.get("Message") or {}).get(kind) or {}
        dim = msg.get("Dimension") or {}
        loa = (dim.get("A") or 0) + (dim.get("B") or 0)
        beam = (dim.get("C") or 0) + (dim.get("D") or 0)
        imo_raw = str(msg.get("ImoNumber") or "")
        imo = imo_raw if imo_check_digit_ok(imo_raw) else None
        ship_type = msg.get("Type")
        vid = vessel_id(imo, mmsi, ctx.scenario_id)
        assert vid is not None
        vessels[mmsi] = VesselRecord(
            id=vid,
            **ctx.lineage(imo or mmsi, available_at=received),
            imo=imo,
            mmsi=mmsi,
            name=(msg.get("Name") or meta.get("ShipName") or "").strip() or None,
            call_sign=(msg.get("CallSign") or "").strip() or None,
            ship_type_ais=ship_type if isinstance(ship_type, int) and ship_type < 100 else None,
            ship_type_group=ais_ship_type_group(ship_type),
            loa_m=float(loa) if 0 < loa < 500 else None,
            beam_m=float(beam) if 0 < beam < 80 else None,
        )

    out: list[Record] = []
    for frame, received in frames:
        kind = frame.get("MessageType")
        if kind not in POSITION_TYPES:
            continue
        meta = frame.get("MetaData") or {}
        mmsi = int(meta.get("MMSI") or 0)
        msg = (frame.get("Message") or {}).get(kind) or {}
        lat, lon = float(msg.get("Latitude", 91)), float(msg.get("Longitude", 181))
        if not 100_000_000 <= mmsi <= 999_999_999 or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue  # 91/181 = position not available
        if mmsi not in vessels:
            vid = vessel_id(None, mmsi, ctx.scenario_id)
            assert vid is not None
            vessels[mmsi] = VesselRecord(
                id=vid,
                **ctx.lineage(mmsi, available_at=received),
                mmsi=mmsi,
                name=(meta.get("ShipName") or "").strip() or None,
            )
        ts = go_time(meta["time_utc"])
        out.append(
            AisPositionRecord(
                id=ctx.rid("ais_position_latest", mmsi),
                **ctx.lineage(f"{mmsi}@{ts.isoformat()}", available_at=received),
                vessel_id=vessels[mmsi].id,
                mmsi=mmsi,
                ts=ts,
                received_at=received,
                msg_type=kind,
                geom=point(lon, lat),
                sog_kn=_none_if(msg.get("Sog"), 102.3),
                cog_deg=_none_if(msg.get("Cog"), 360.0),
                heading_deg=_none_if(msg.get("TrueHeading"), 511.0),
                nav_status=msg.get("NavigationalStatus"),
            )
        )
    return list(vessels.values()) + out


# --- Global Fishing Watch (DS-AIS-02, DS-SAT-04) ---------------------------------------------

# GFW port IDs → UN/LOCODE (PROBE_REPORT: GFW calls Chattogram "bgd-chittagong").
GFW_PORTS = {"bgd-chittagong": "BDCGP", "bgd-mongla": "BDMGL", "bgd-payra": "BDPAY"}
GFW_TYPES = {
    "cargo": ShipTypeGroup.CARGO,
    "carrier": ShipTypeGroup.CARGO,
    "tanker": ShipTypeGroup.TANKER,
    "passenger": ShipTypeGroup.PASSENGER,
    "fishing": ShipTypeGroup.FISHING,
    "support": ShipTypeGroup.TUG_SERVICE,
    "bunker": ShipTypeGroup.TANKER,
}
PORT_VISIT_LAG_H = 72  # measured 2–4 days
PRESENCE_LAG_H = 96
SAR_LAG_H = 9 * 24
LONG_STAY_H = 60 * 24  # SC-04


def _json(body: bytes) -> Any:
    """GFW report bodies are JSON, or a zip holding JSON (4Wings); sniff instead of trusting
    the file extension."""
    if body[:2] == b"PK":
        archive = zipfile.ZipFile(io.BytesIO(body))
        name = next(n for n in archive.namelist() if n.endswith(".json"))
        return json.loads(archive.read(name))
    return json.loads(body)


def _report_rows(doc: Any) -> list[dict[str, Any]]:
    """4Wings report rows: `entries[0][<dataset>]` lists, flattened."""
    rows: list[dict[str, Any]] = []
    for entry in doc.get("entries", []) if isinstance(doc, dict) else []:
        for value in entry.values():
            if isinstance(value, list):
                rows += [r for r in value if isinstance(r, dict)]
    return rows


def parse_gfw_port_visits(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = _json(body)
    window_start = parse_ts(((doc.get("metadata") or {}).get("dateRange") or {}).get("from"))
    out: list[Record] = []
    vessels: dict[Any, VesselRecord] = {}
    for entry in doc.get("entries", []):
        visit = entry.get("port_visit") or {}
        stops_raw: list[dict[str, Any]] = [
            s
            for s in (
                visit.get(k) for k in ("startAnchorage", "intermediateAnchorage", "endAnchorage")
            )
            if s
        ]
        locode = next((GFW_PORTS[s["id"]] for s in stops_raw if s.get("id") in GFW_PORTS), None)
        vessel = entry.get("vessel") or {}
        if not locode or not vessel.get("ssvid"):
            continue
        mmsi = int(vessel["ssvid"]) if str(vessel["ssvid"]).isdigit() else None
        if mmsi is None or not 100_000_000 <= mmsi <= 999_999_999:
            continue
        vid = vessel_id(None, mmsi, ctx.scenario_id)
        assert vid is not None
        start, end = parse_ts(entry.get("start")), parse_ts(entry.get("end"))
        duration_h = float(visit.get("durationHrs") or 0) or None
        confidence = int(visit.get("confidence") or 0) or None
        flags: list[str] = []
        if duration_h and duration_h > LONG_STAY_H:
            flags.append(PortCallFlag.LONG_STAY)
        if window_start and start and start < window_start:
            flags.append(PortCallFlag.WINDOW_OVERLAP)
        if confidence is not None and confidence < 4:
            flags.append(PortCallFlag.LOW_CONFIDENCE)
        at_dock = any(s.get("atDock") for s in stops_raw)
        call_id = ctx.rid("port_call", entry["id"])
        out.append(
            PortCallRecord(
                id=call_id,
                **ctx.lineage(entry["id"], available_at=lagged(end, PORT_VISIT_LAG_H)),
                vessel_id=vid,
                port_id=port_id(locode),
                status=PortCallStatus.COMPLETED if end else PortCallStatus.ACTIVE,
                visit_kind=VisitKind.BERTH_CALL if at_dock else VisitKind.ANCHORAGE_ONLY,
                arrival_ts=start,
                anchorage_start_ts=start,
                departure_ts=end,
                dwell_h=duration_h,
                censored=end is None,
                method=PortCallMethod.GFW,
                confidence=confidence,
                gfw_visit_id=visit.get("visitId"),
                quality_flags=flags,
            )
        )
        previous = None
        for seq, stop in enumerate(stops_raw):
            key = (stop.get("anchorageId"), stop.get("atDock"))
            if key == previous:
                continue  # GFW repeats the start cell as "intermediate" on one-stop visits
            previous = key
            out.append(
                PortCallStopRecord(
                    id=ctx.rid("port_call_stop", f"{entry['id']}:{seq}"),
                    **ctx.lineage(
                        f"{entry['id']}:{seq}", available_at=lagged(end, PORT_VISIT_LAG_H)
                    ),
                    port_call_id=call_id,
                    seq=seq,
                    cell_id=stop.get("anchorageId"),
                    at_dock=bool(stop.get("atDock")),
                    geom=point(float(stop["lon"]), float(stop["lat"])),
                )
            )
        vessels[vid] = VesselRecord(
            id=vid,
            **ctx.lineage(mmsi),
            mmsi=mmsi,
            name=vessel.get("name"),
            ship_type_group=GFW_TYPES.get(str(vessel.get("type") or "").lower()),
            flag_iso3=vessel.get("flag") if len(str(vessel.get("flag") or "")) == 3 else None,
        )
    return list(vessels.values()) + out


def parse_gfw_presence(body: bytes, ctx: ParseContext, area: str) -> list[Record]:
    out: list[Record] = []
    vessels: dict[Any, VesselRecord] = {}
    for row in _report_rows(_json(body)):
        mmsi = int(row["mmsi"]) if str(row.get("mmsi") or "").isdigit() else None
        imo = str(row.get("imo") or "") or None
        imo = imo if imo and imo_check_digit_ok(imo) else None
        day = date.fromisoformat(str(row["date"])[:10])
        kind = str(row.get("vesselType") or row.get("geartype") or "").lower()
        vid = vessel_id(imo, mmsi, ctx.scenario_id)
        day_end = datetime.combine(day, time(23, 59), UTC)
        out.append(
            ZonePresenceDailyRecord(
                id=ctx.rid("zone_presence_daily", f"{area}:{day}:{row.get('vesselId')}"),
                **ctx.lineage(f"{day}:{row.get('vesselId')}", lagged(day_end, PRESENCE_LAG_H)),
                area_name=area,
                date=day,
                vessel_id=vid,
                mmsi=mmsi,
                imo=imo,
                ship_type_group=GFW_TYPES.get(kind),
                hours=min(float(row.get("hours") or 0), 24.0),
                mean_sog_kn=float(row["speed"]) if row.get("speed") is not None else None,
                entry_ts=parse_ts(row.get("entryTimestamp")),
                exit_ts=parse_ts(row.get("exitTimestamp")),
            )
        )
        if vid is not None and (mmsi or imo):
            vessels[vid] = VesselRecord(
                id=vid,
                **ctx.lineage(imo or mmsi),
                imo=imo,
                mmsi=mmsi,
                name=row.get("shipName"),
                call_sign=row.get("callsign"),
                ship_type_group=GFW_TYPES.get(kind),
                flag_iso3=row.get("flag") if len(str(row.get("flag") or "")) == 3 else None,
            )
    return list(vessels.values()) + out


def parse_gfw_sar(body: bytes, ctx: ParseContext, area: str) -> list[Record]:
    """Daily SAR detections in an area; rows come per (date, flag), summed per day."""
    per_day: dict[str, list[dict[str, Any]]] = {}
    for row in _report_rows(_json(body)):
        per_day.setdefault(str(row["date"])[:10], []).append(row)
    out: list[Record] = []
    for day, rows in sorted(per_day.items()):
        acq = datetime.combine(date.fromisoformat(day), time(0), UTC)
        out.append(
            SatelliteObservationRecord(
                id=ctx.rid("satellite_observation", f"{area}:{day}"),
                **ctx.lineage(f"{area}:{day}", available_at=lagged(acq, SAR_LAG_H)),
                sensor=SatelliteSensor.GFW_SAR,
                acq_ts=acq,
                area_name=area,
                detections_count=sum(int(r.get("detections") or 0) for r in rows),
                detections=[
                    {"flag": r.get("flag"), "detections": r.get("detections")} for r in rows
                ],
            )
        )
    return out


def parse_gfw_vessel_identity(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = json.loads(body)
    out: list[Record] = []
    for info in doc.get("selfReportedInfo", []):
        ssvid = str(info.get("ssvid") or "")
        if not ssvid.isdigit():
            continue
        imo = str(info.get("imo") or "") or None
        imo = imo if imo and imo_check_digit_ok(imo) else None
        vid = vessel_id(imo, int(ssvid), ctx.scenario_id)
        assert vid is not None
        out.append(
            VesselRecord(
                id=vid,
                **ctx.lineage(info.get("id")),
                imo=imo,
                mmsi=int(ssvid),
                name=info.get("shipname"),
                call_sign=info.get("callsign"),
                flag_iso3=info.get("flag") if len(str(info.get("flag") or "")) == 3 else None,
            )
        )
    return out
