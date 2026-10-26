"""Weather (Open-Meteo), hazard events (GDACS), holidays and FDA regulatory events."""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cportal_core.enums import (
    AlertLevel,
    DisruptionType,
    EventStatus,
    HolidayKind,
    WeatherKind,
)
from cportal_core.schemas.records import (
    DisruptionEventRecord,
    HolidayRecord,
    Record,
    WeatherObservationRecord,
    point,
)

from cportal_connectors.canonical import ParseContext, lagged, parse_ts
from cportal_connectors.parsers.ports import ALERT_SEVERITY, GDACS_TYPES

# --- Open-Meteo (DS-WX-01) ----------------------------------------------------------------------

ARCHIVE_LAG_H = 5 * 24  # the reanalysis archive trails real time by ~5 days
# Open-Meteo variable → (record field, unit the record expects).
WEATHER_FIELDS = {
    "temperature_2m": ("temperature_2m_c", "°C"),
    "precipitation": ("precipitation_mm", "mm"),
    "wind_speed_10m": ("wind_speed_10m_kmh", "km/h"),
    "wind_gusts_10m": ("wind_gusts_10m_kmh", "km/h"),
    "wind_direction_10m": ("wind_direction_10m_deg", "°"),
    "pressure_msl": ("pressure_msl_hpa", "hPa"),
    "wave_height": ("wave_height_m", "m"),
    "wave_period": ("wave_period_s", "s"),
    "swell_wave_height": ("swell_wave_height_m", "m"),
    "sea_level_height_msl": ("sea_level_height_msl_m", "m"),
    "ocean_current_velocity": ("ocean_current_velocity_kmh", "km/h"),
}


def parse_open_meteo(
    body: bytes, ctx: ParseContext, point_name: str, kind: WeatherKind
) -> list[Record]:
    """Hourly arrays → one record per hour. Units are checked against `hourly_units` so a
    request without the expected unit parameters fails loudly instead of mixing units."""
    doc = json.loads(body)
    hourly: dict[str, list[Any]] = doc.get("hourly") or {}
    units: dict[str, str] = doc.get("hourly_units") or {}
    offset = timedelta(seconds=int(doc.get("utc_offset_seconds") or 0))
    for variable, (_, unit) in WEATHER_FIELDS.items():
        if variable in hourly and units.get(variable) not in (unit, None):
            raise ValueError(f"{variable}: expected {unit}, got {units.get(variable)}")
    where = point(float(doc["longitude"]), float(doc["latitude"]))
    archive = kind in (WeatherKind.ARCHIVE, WeatherKind.MARINE_ARCHIVE)
    vintage = "" if archive else f"@{ctx.fetched_at.isoformat() if ctx.fetched_at else ''}"
    out: list[Record] = []
    for i, stamp in enumerate(hourly.get("time", [])):
        ts = datetime.fromisoformat(stamp).replace(tzinfo=UTC) - offset
        values = {
            field: hourly[variable][i]
            for variable, (field, _) in WEATHER_FIELDS.items()
            if variable in hourly and hourly[variable][i] is not None
        }
        out.append(
            WeatherObservationRecord(
                # One row per hour for archives; forecasts keep every issue (vintage).
                id=ctx.rid("weather_observation", f"{point_name}:{kind}:{ts.isoformat()}{vintage}"),
                **ctx.lineage(
                    f"{point_name}:{ts.isoformat()}",
                    available_at=lagged(ts, ARCHIVE_LAG_H) if archive else ctx.fetched_at,
                ),
                point_name=point_name,
                geom=where,
                ts=ts,
                kind=kind,
                issued_at=None if archive else ctx.fetched_at,
                **values,
            )
        )
    return out


# --- GDACS (DS-WX-02) ---------------------------------------------------------------------------

GDACS_LAG_H = 1


def _maybe_literal(value: Any) -> Any:
    """GDACS sometimes serialises nested objects as Python-literal strings."""
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    return value


def parse_gdacs(body: bytes, ctx: ParseContext) -> list[Record]:
    """GDACS GeoJSON (a FeatureCollection, or a single Feature for one event). GDACS answers
    204 with an empty body when nothing matches (PROBE_REPORT), which means "no events"."""
    if not body.strip():
        return []
    doc = json.loads(body)
    features = doc.get("features") if doc.get("type") == "FeatureCollection" else [doc]
    out: list[Record] = []
    for feature in features or []:
        p = feature.get("properties") or {}
        kind = GDACS_TYPES.get(str(p.get("eventtype")))
        if kind is None:
            continue
        level = AlertLevel(str(p.get("alertlevel") or "Green").lower())
        start, end = parse_ts(p.get("fromdate")), parse_ts(p.get("todate"))
        countries = _maybe_literal(p.get("affectedcountries")) or []
        severity = _maybe_literal(p.get("severitydata")) or {}
        urls = _maybe_literal(p.get("url")) or {}
        key = f"{p.get('eventtype')}:{p.get('eventid')}"
        geometry = feature.get("geometry")
        out.append(
            DisruptionEventRecord(
                id=ctx.rid("disruption_event", key),
                **ctx.lineage(key, available_at=lagged(start, GDACS_LAG_H)),
                type=kind,
                subtype=str(p.get("eventtype")),
                title=str(p.get("name") or p.get("eventname") or key),
                summary=p.get("htmldescription")
                or (severity.get("severitytext") if isinstance(severity, dict) else None),
                status=EventStatus.ONGOING
                if str(p.get("iscurrent")).lower() == "true"
                else EventStatus.RESOLVED,
                severity=ALERT_SEVERITY[level],
                confidence=0.9,
                alert_level=level,
                start_est=start,
                end_est=end,
                geom=geometry if (geometry or {}).get("type") == "Point" else None,
                country_iso3=[c["iso3"] for c in countries if isinstance(c, dict) and c.get("iso3")]
                or ([p["iso3"]] if p.get("iso3") else []),
                first_seen=start,
                last_updated=parse_ts(p.get("datemodified")),
                external_ids={
                    "gdacs": str(p.get("eventid")),
                    "gdacs_episode": str(p.get("episodeid")),
                    **({"glide": p["glide"]} if p.get("glide") else {}),
                },
                url=urls.get("report") if isinstance(urls, dict) else None,
            )
        )
    return out


# --- holidays package (DS-WX-04) ----------------------------------------------------------------


def parse_holidays(body: bytes, ctx: ParseContext) -> list[Record]:
    """`[{date, name}]` from the `holidays` package (public holidays; extended closures and
    truck bans come from the manual table, SC-12). Known in advance: available_at is null."""
    return [
        HolidayRecord(
            id=ctx.rid("holiday", f"BD:{row['date']}:{row['name']}"),
            **{**ctx.lineage(f"{row['date']}:{row['name']}"), "available_at": None},
            date=date.fromisoformat(row["date"]),
            kind=HolidayKind.PUBLIC,
            name=row["name"],
            country_iso2="BD",
        )
        for row in json.loads(body)
    ]


# --- openFDA (DS-PHARMA-01) ---------------------------------------------------------------------

RECALL_SEVERITY = {"Class I": 0.9, "Class II": 0.6, "Class III": 0.3}
RECALL_STATUS = {
    "Ongoing": EventStatus.ONGOING,
    "Completed": EventStatus.RESOLVED,
    "Terminated": EventStatus.RESOLVED,
}
COUNTRY_ISO3 = {"India": "IND", "Bangladesh": "BGD", "China": "CHN", "United States": "USA"}


def _yyyymmdd(text: Any) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(str(text), "%Y%m%d").replace(tzinfo=UTC)


def _mdy(text: Any) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(str(text), "%m/%d/%Y").replace(tzinfo=UTC)


def parse_openfda_recalls(body: bytes, ctx: ParseContext) -> list[Record]:
    """Drug enforcement reports → PHARMA_REGULATORY_QUALITY events. Real firms appear with
    sourced facts only (03 §5)."""
    out: list[Record] = []
    for r in json.loads(body).get("results", []):
        number = r.get("recall_number")
        if not number:
            continue
        firm = r.get("recalling_firm") or "unknown firm"
        product = " ".join(str(r.get("product_description") or "").split())[:120]
        start = _yyyymmdd(r.get("recall_initiation_date"))
        out.append(
            DisruptionEventRecord(
                id=ctx.rid("disruption_event", number),
                **ctx.lineage(number, available_at=_yyyymmdd(r.get("report_date"))),
                type=DisruptionType.PHARMA_REGULATORY_QUALITY,
                subtype=f"fda_recall_{str(r.get('classification', '')).lower().replace(' ', '_')}",
                title=f"{r.get('classification', 'FDA')} recall by {firm}: {product}",
                summary=" ".join(str(r.get("reason_for_recall") or "").split())[:1000] or None,
                status=RECALL_STATUS.get(str(r.get("status")), EventStatus.REPORTED),
                severity=RECALL_SEVERITY.get(str(r.get("classification"))),
                confidence=1.0,
                start_est=start,
                end_est=_yyyymmdd(r.get("termination_date")),
                country_iso3=[COUNTRY_ISO3[c]] if (c := r.get("country")) in COUNTRY_ISO3 else [],
                first_seen=_yyyymmdd(r.get("report_date")),
                external_ids={"fda_recall": number, "fda_event": r.get("event_id")},
            )
        )
    return out


def parse_openfda_shortages(body: bytes, ctx: ParseContext) -> list[Record]:
    out: list[Record] = []
    for r in json.loads(body).get("results", []):
        ndc = r.get("package_ndc")
        name = r.get("generic_name")
        if not ndc or not name:
            continue
        posted = _mdy(r.get("initial_posting_date"))
        updated = _mdy(r.get("update_date")) or posted
        current = str(r.get("status") or "").lower() == "current"
        out.append(
            DisruptionEventRecord(
                id=ctx.rid("disruption_event", f"shortage:{ndc}"),
                **ctx.lineage(ndc, available_at=updated),
                type=DisruptionType.SUPPLIER_INCIDENT,
                subtype="drug_shortage",
                title=f"Drug shortage: {name}",
                summary=r.get("shortage_reason") or r.get("availability"),
                status=EventStatus.ONGOING if current else EventStatus.RESOLVED,
                confidence=1.0,
                start_est=posted,
                country_iso3=["USA"],
                first_seen=posted,
                last_updated=updated,
                external_ids={"fda_shortage_ndc": ndc},
            )
        )
    return out
