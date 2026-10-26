"""PortWatch, UN/LOCODE, OSM port geometry (Overpass) and searoute sea lanes."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, date, datetime, time
from typing import Any

from cportal_core.enums import (
    AlertLevel,
    DisruptionType,
    EventStatus,
    LocationKind,
    PortType,
    TransportMode,
    ZoneType,
)
from cportal_core.ids import entity_id, location_id, normalize_locode, port_id
from cportal_core.schemas.records import (
    DisruptionEventRecord,
    ExternalIdRecord,
    LaneRecord,
    LocationRecord,
    PortActivityDailyRecord,
    PortRecord,
    PortZoneRecord,
    Record,
    point,
)

from cportal_connectors.canonical import ParseContext, lagged, parse_ts

# --- IMF PortWatch (DS-PORT-01) ----------------------------------------------------------------

# PortWatch IDs → UN/LOCODE. PortWatch's LOCODE field is null or space-formatted for Bangladesh
# (PROBE_REPORT S6), so the join is by port name, checked once here.
PORTWATCH_PORTS = {
    "port241": "BDCGP",  # Chittagong
    "port289": "BDDAC",  # Dhaka (river port)
    "port759": "BDMGL",  # Mongla
    "port890": "BDPAY",  # Payra
}
PORTWATCH_LAG_H = 10 * 24  # daily estimates appear ~10 days later
VESSEL_TYPES = ("container", "dry_bulk", "general_cargo", "roro", "tanker")
GDACS_TYPES = {
    "TC": DisruptionType.CYCLONE_STORM,
    "FL": DisruptionType.FLOOD,
    "EQ": DisruptionType.EARTHQUAKE_OTHER_NATURAL,
    "DR": DisruptionType.EARTHQUAKE_OTHER_NATURAL,
    "VO": DisruptionType.EARTHQUAKE_OTHER_NATURAL,
    "WF": DisruptionType.FIRE_EXPLOSION,
}
ALERT_SEVERITY = {AlertLevel.GREEN: 0.2, AlertLevel.ORANGE: 0.6, AlertLevel.RED: 0.9}


def _features(body: bytes) -> list[dict[str, Any]]:
    doc = json.loads(body)
    return [f.get("attributes") or {} for f in doc.get("features", [])]


def parse_portwatch_daily(body: bytes, ctx: ParseContext) -> list[Record]:
    out: list[Record] = []
    for a in _features(body):
        locode = PORTWATCH_PORTS.get(str(a.get("portid")))
        if not locode:
            continue
        day = date.fromisoformat(str(a["date"])[:10])
        out.append(
            PortActivityDailyRecord(
                id=ctx.rid("port_activity_daily", f"{a['portid']}:{day}"),
                **ctx.lineage(
                    f"{a['portid']}:{day}",
                    available_at=lagged(datetime.combine(day, time(23, 59), UTC), PORTWATCH_LAG_H),
                ),
                port_id=port_id(locode),
                date=day,
                calls_total=a.get("portcalls"),
                calls_by_type={t: int(a.get(f"portcalls_{t}") or 0) for t in VESSEL_TYPES},
                import_t=a.get("import"),
                export_t=a.get("export"),
                trade_by_type={
                    **{f"import_{t}": float(a.get(f"import_{t}") or 0) for t in VESSEL_TYPES},
                    **{f"export_{t}": float(a.get(f"export_{t}") or 0) for t in VESSEL_TYPES},
                },
            )
        )
    return out


def parse_portwatch_ports(body: bytes, ctx: ParseContext) -> list[Record]:
    """PortWatch port IDs as external identifiers of our UN/LOCODE-keyed ports (SC-02)."""
    out: list[Record] = []
    for a in _features(body):
        locode = PORTWATCH_PORTS.get(str(a.get("portid"))) or normalize_locode(a.get("LOCODE"))
        if not locode:
            continue
        out.append(
            ExternalIdRecord(
                id=ctx.rid("external_id", f"port:portwatch:{a['portid']}"),
                **ctx.lineage(a["portid"]),
                entity_type="port",
                entity_id=port_id(locode),
                scheme="portwatch",
                value=str(a["portid"]),
            )
        )
    return out


def parse_portwatch_disruptions(body: bytes, ctx: ParseContext) -> list[Record]:
    out: list[Record] = []
    for a in _features(body):
        kind = GDACS_TYPES.get(str(a.get("eventtype")))
        if kind is None:
            continue
        level = AlertLevel(str(a.get("alertlevel") or "green").lower())
        start, end = parse_ts(a.get("fromdate")), parse_ts(a.get("todate"))
        ports = [p.strip() for p in str(a.get("affectedports") or "").split(",") if p.strip()]
        out.append(
            DisruptionEventRecord(
                id=ctx.rid("disruption_event", a["eventid"]),
                **ctx.lineage(a["eventid"], available_at=parse_ts(a.get("editdate"))),
                type=kind,
                title=str(a.get("htmlname") or a.get("eventname")),
                summary=a.get("htmldescription"),
                status=EventStatus.RESOLVED
                if end and end < (ctx.fetched_at or end)
                else EventStatus.ONGOING,
                severity=ALERT_SEVERITY[level],
                confidence=0.9,
                alert_level=level,
                start_est=start,
                end_est=end,
                geom=point(float(a["long"]), float(a["lat"]))
                if a.get("long") is not None
                else None,
                locodes=[PORTWATCH_PORTS[p] for p in ports if p in PORTWATCH_PORTS],
                country_iso3=["BGD"] if a.get("country") == "Bangladesh" else [],
                first_seen=start,
                last_updated=parse_ts(a.get("editdate")),
                external_ids={"gdacs": str(a["eventid"]), "portwatch": a.get("pageid")},
            )
        )
    return out


# --- UN/LOCODE (DS-PORT-05) ----------------------------------------------------------------------

SEAPORTS = {"BDCGP", "BDMGL", "BDPAY"}  # the brief's three seaports (D-01)
# Ports that UN/LOCODE lists without a port function but other sources treat as ports
# (PortWatch "Dhaka" = the river port at Dhaka). The location keeps its UN/LOCODE kind.
EXTRA_PORTS = {"BDDAC": PortType.RIVER}
_COORD = re.compile(r"^(\d{2})(\d{2})([NS]) (\d{3})(\d{2})([EW])$")


def unlocode_point(text: str | None) -> tuple[float, float] | None:
    """'2220N 09150E' → (lon, lat) in decimal degrees."""
    match = _COORD.match((text or "").strip())
    if not match:
        return None
    lat_d, lat_m, ns, lon_d, lon_m, ew = match.groups()
    lat = (int(lat_d) + int(lat_m) / 60) * (1 if ns == "N" else -1)
    lon = (int(lon_d) + int(lon_m) / 60) * (1 if ew == "E" else -1)
    return round(lon, 4), round(lat, 4)


def _unlocode_kind(locode: str, function: str) -> LocationKind:
    if locode in SEAPORTS:
        return LocationKind.SEAPORT
    if function[:1] == "1":
        return LocationKind.RIVER_PORT
    if "6" in function or "3" in function[2:3]:
        return LocationKind.ICD
    if function[1:2] == "2":
        return LocationKind.RAIL_HUB
    return LocationKind.CITY


def parse_unlocode_csv(body: bytes, ctx: ParseContext) -> list[Record]:
    """UN/LOCODE rows → locations, plus a port row for every port/ICD function (Function
    precedes Status in the 2024+ layout; A-009)."""
    out: list[Record] = []
    for row in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
        if row.get("Change") == "X":  # marked for deletion
            continue
        locode = normalize_locode(f"{row['Country']}{row['Location']}")
        if not locode:
            continue
        function = row.get("Function") or ""
        kind = _unlocode_kind(locode, function)
        coords = unlocode_point(row.get("Coordinates"))
        loc_id = location_id(locode)
        out.append(
            LocationRecord(
                id=loc_id,
                **ctx.lineage(locode),
                locode=locode,
                name=row["Name"],
                country_iso2=row["Country"],
                kind=kind,
                geom=point(*coords) if coords else None,
                attrs={
                    "function": function,
                    "status": row.get("Status"),
                    "subdivision": row.get("Subdivision") or None,
                    "iata": row.get("IATA") or None,
                },
            )
        )
        port_type = EXTRA_PORTS.get(locode) or {
            LocationKind.SEAPORT: PortType.SEA,
            LocationKind.RIVER_PORT: PortType.RIVER,
            LocationKind.ICD: PortType.ICD,
        }.get(kind)
        if port_type is not None:
            out.append(
                PortRecord(
                    id=port_id(locode),
                    **ctx.lineage(locode),
                    location_id=loc_id,
                    locode=locode,
                    name=row["Name"],
                    port_type=port_type,
                    tidal=locode in SEAPORTS,
                )
            )
    return out


# --- OSM port geometry via Overpass (DS-PORT-06) -----------------------------------------------


def _osm_point(element: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lon"]), float(element["lat"])
    center = element.get("center")
    if center:
        return float(center["lon"]), float(center["lat"])
    return None


def _zone_type(tags: dict[str, str]) -> ZoneType | None:
    seamark = tags.get("seamark:type", "")
    if "anchorage" in seamark:
        return ZoneType.ANCHORAGE
    if seamark in ("berth", "mooring") or tags.get("man_made") in ("pier", "quay", "jetty"):
        return ZoneType.BERTH
    if tags.get("landuse") == "port" or tags.get("industrial") == "port" or tags.get("port"):
        return ZoneType.TERMINAL
    if tags.get("harbour") or seamark == "harbour":
        return ZoneType.PORT_LIMIT
    if tags.get("waterway") in ("fairway", "canal") or seamark == "fairway":
        return ZoneType.CHANNEL
    return None


def parse_overpass_port_zones(body: bytes, ctx: ParseContext, locode: str) -> list[Record]:
    """OSM features around a port → zones. Overpass `out center` gives one point per way; the
    polygons themselves come from the Geofabrik extract in M2 (A-014)."""
    out: list[Record] = []
    for element in json.loads(body).get("elements", []):
        tags = element.get("tags") or {}
        zone = _zone_type(tags)
        where = _osm_point(element)
        if zone is None or where is None:
            continue
        osm_ref = f"{element['type']}/{element['id']}"
        out.append(
            PortZoneRecord(
                id=ctx.rid("port_zone", osm_ref),
                **ctx.lineage(osm_ref),
                port_id=port_id(locode),
                zone_type=zone,
                name=tags.get("name") or tags.get("seamark:name") or f"OSM {osm_ref}",
                geom=point(*where),
                attrs={
                    "osm": osm_ref,
                    "tags": {
                        k: v for k, v in tags.items() if ":" not in k or k.startswith("seamark")
                    },
                },
            )
        )
    return out


# --- searoute (DS-PORT-08) ----------------------------------------------------------------------

NM_TO_KM = 1.852


def _wrap(lon: float) -> float:
    """searoute returns unwrapped longitudes past the antimeridian (e.g. 241.73)."""
    return ((lon + 180) % 360) - 180


def parse_searoute_routes(body: bytes, ctx: ParseContext) -> list[Record]:
    """Sea lanes from BDCGP to the transshipment hubs, plus minimal locations for the foreign
    hubs so the lane's foreign keys hold before those countries' UN/LOCODE lists are loaded."""
    out: list[Record] = []
    for feature in json.loads(body).get("features", []):
        props = feature.get("properties") or {}
        origin = normalize_locode(str(props.get("from", "")).split(" ")[0])
        dest_text = str(props.get("to", ""))
        dest = normalize_locode(dest_text.split(" ")[0])
        coords = [
            [round(_wrap(float(c[0])), 6), float(c[1])]
            for c in (feature.get("geometry") or {}).get("coordinates") or []
        ]
        if not origin or not dest or len(coords) < 2:
            continue
        endpoints = ((origin, origin, coords[0]), (dest, dest_text[6:] or dest, coords[-1]))
        for code, name, where in endpoints:
            if code.startswith("BD"):
                continue  # Bangladeshi locations come from UN/LOCODE; never rename them here
            out.append(
                LocationRecord(
                    id=location_id(code),
                    **ctx.lineage(code),
                    locode=code,
                    name=name,
                    country_iso2=code[:2],
                    kind=LocationKind.SEAPORT,
                    geom=point(float(where[0]), float(where[1])),
                )
            )
        length = float(props.get("length") or 0)
        km = length * NM_TO_KM if props.get("units", "naut").startswith("naut") else length
        hours = props.get("duration_hours")
        out.append(
            LaneRecord(
                id=ctx.rid("lane", f"{origin}->{dest}"),
                **ctx.lineage(f"{origin}->{dest}"),
                origin_location_id=location_id(origin),
                dest_location_id=location_id(dest),
                mode=TransportMode.SEA,
                distance_km=round(km, 1),
                typical_transit_d=round(float(hours) / 24, 2) if hours else None,
                geom={"type": "LineString", "coordinates": coords},
            )
        )
    return out


def external_port_ids(ctx: ParseContext, scheme: str, mapping: dict[str, str]) -> list[Record]:
    """Static cross-walks (e.g. GFW port IDs) as external_id rows."""
    return [
        ExternalIdRecord(
            id=ctx.rid("external_id", f"port:{scheme}:{value}"),
            **ctx.lineage(value),
            entity_type="port",
            entity_id=entity_id("port", "unlocode", locode),
            scheme=scheme,
            value=value,
        )
        for value, locode in mapping.items()
    ]
