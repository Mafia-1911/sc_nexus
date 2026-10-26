"""Synthetic twins per source (D-08, ADR-010): render the source's own wire format, then run the
source's real parser with a synthetic ParseContext. Live, replay and synthetic data therefore go
through identical code and land in identical canonical records (`is_synthetic`, `scenario_id`).

Port twins are driven by the DES; hazard and news twins by the scenario. Outlets use reserved
`.example` domains; every firm named in synthetic text is fictional (AGENTS.md rule 3).
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_connectors.ais_synthetic import frames_for_hour
from cportal_connectors.canonical import ParseContext, scenario_uuid
from cportal_connectors.parsers.hazards import (
    parse_gdacs,
    parse_open_meteo,
    parse_openfda_recalls,
)
from cportal_connectors.parsers.maritime import (
    parse_aisstream_jsonl,
    parse_gfw_port_visits,
    parse_gfw_presence,
    parse_gfw_sar,
)
from cportal_connectors.parsers.news import (
    parse_gdelt_doc,
    parse_gdelt_gkg,
    parse_reliefweb_reports,
    parse_rss,
)
from cportal_connectors.parsers.ports import (
    parse_portwatch_daily,
    parse_portwatch_disruptions,
)
from cportal_connectors.sources.ds_news_02_gdelt_files import GKG_COLUMNS
from cportal_core.enums import DataMode, WeatherKind
from cportal_core.schemas.records import Record

from cportal_sim.port_des import DesResult, present_on, to_twin_visit

GENERATOR = "cportal-sim/twins/0.1.0"
AREA = "ctg_outer_anchorage"
GFW_PORT = "bgd-chittagong"
SAR_DETECTION_P = {"small": 0.55, "large": 0.92}  # Sentinel-1 misses many small craft (estimate)


def ctx(ds_id: str, scenario: str, fetched_at: datetime | None = None) -> ParseContext:
    return ParseContext(
        ds_id,
        DataMode.SYNTHETIC,
        fetched_at=fetched_at,
        scenario_id=scenario_uuid(scenario),
        generator_version=GENERATOR,
    )


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- DS-AIS-01 aisstream --------------------------------------------------------------------------


def aisstream(result: DesResult, scenario: str, hour: datetime) -> list[Record]:
    """One hour of frames in aisstream's envelope format, through the real AIS parser."""
    visits = [
        to_twin_visit(v, result.priors, result.seed)
        for v in result.visits
        if v.arrive - timedelta(hours=12) < hour + timedelta(hours=1) and v.depart > hour
    ]
    rows = frames_for_hour(visits, hour, result.priors, result.seed, scenario)
    body = "\n".join(json.dumps(r) for r in rows).encode()
    return parse_aisstream_jsonl(body, ctx("DS-AIS-01", scenario))


# --- DS-AIS-02 Global Fishing Watch ---------------------------------------------------------------


def _anchorage(cell: dict[str, Any], at_dock: bool = False) -> dict[str, Any]:
    return {
        "anchorageId": cell["id"],
        "atDock": at_dock,
        "distanceFromShoreKm": "0" if at_dock else "12",
        "flag": "BGD",
        "id": GFW_PORT,
        "lat": cell["lat"],
        "lon": cell["lon"],
        "name": "CHITTAGONG",
        "topDestination": "CHITTAGONG",
    }


def gfw_port_visits(result: DesResult, scenario: str, until: datetime) -> list[Record]:
    """Completed visits in the window as GFW port-visit events (vessel type `cargo`)."""
    entries = []
    for v in result.in_window():
        if v.depart > until:
            continue
        berth = None
        if v.mode == "berth":
            cells = (
                result.priors["berth_cells"].get(v.kind)
                or result.priors["berth_cells"]["general_cargo"]
            )
            berth = cells[v.index % len(cells)]
        start_cell = _anchorage(v.anchorage)
        mid = _anchorage(berth, at_dock=True) if berth else start_cell
        end = v.berth_end or v.leave_anchorage
        visit_id = f"syn{v.index:08d}{result.seed:04d}"
        entries.append(
            {
                "start": _iso(v.arrive),
                "end": _iso(end),
                "id": visit_id,
                "type": "port_visit",
                "position": {"lat": v.spot[0], "lon": v.spot[1]},
                "vessel": {
                    "id": f"syn-{v.vessel.mmsi}",
                    "name": v.vessel.name,
                    "ssvid": str(v.vessel.mmsi),
                    "flag": None,
                    "type": "cargo",
                },
                "port_visit": {
                    "visitId": visit_id,
                    "confidence": "4",
                    "durationHrs": round(v.dwell_h, 3),
                    "startAnchorage": start_cell,
                    "intermediateAnchorage": mid,
                    "endAnchorage": mid if berth else start_cell,
                },
            }
        )
    doc = {
        "metadata": {"dateRange": {"from": _iso(result.start), "to": _iso(until)}},
        "entries": entries,
        "total": len(entries),
    }
    return parse_gfw_port_visits(json.dumps(doc).encode(), ctx("DS-AIS-02", scenario))


def gfw_presence(result: DesResult, scenario: str, until: datetime) -> list[Record]:
    rows = []
    day = result.start
    while day < until:
        for v, hours in present_on(result, day):
            rows.append(
                {
                    "date": day.date().isoformat(),
                    "vesselId": f"syn-{v.vessel.mmsi}",
                    "mmsi": str(v.vessel.mmsi),
                    "imo": None,
                    "shipName": v.vessel.name,
                    "callsign": v.vessel.callsign,
                    "flag": None,
                    "vesselType": "CARGO",
                    "hours": round(hours, 2),
                    "speed": 0.2,
                    "entryTimestamp": _iso(v.arrive),
                    "exitTimestamp": _iso(v.leave_anchorage),
                }
            )
        day += timedelta(days=1)
    doc = {"total": 1, "entries": [{"public-global-presence:v5.0": rows}]}
    return parse_gfw_presence(json.dumps(doc).encode(), ctx("DS-AIS-02", scenario), area=AREA)


def gfw_sar(result: DesResult, scenario: str, until: datetime, every_days: int = 4) -> list[Record]:
    """Sentinel-1 passes every few days at ~23:50 UTC; detection odds depend on vessel size."""
    rng = random.Random(f"{result.seed}:sar")
    rows = []
    day = result.start
    while day < until:
        pass_ts = day + timedelta(hours=23, minutes=50)
        detected = 0
        for v in result.visits:
            if v.arrive <= pass_ts < v.leave_anchorage:
                p = SAR_DETECTION_P["large" if v.vessel.loa >= 100 else "small"]
                detected += rng.random() < p
        rows.append(
            {
                "date": day.date().isoformat(),
                "detections": detected,
                "flag": None,
                "vesselIDs": detected,
            }
        )
        day += timedelta(days=every_days)
    doc = {"total": 1, "entries": [{"public-global-sar-presence:v5.0": rows}]}
    return parse_gfw_sar(json.dumps(doc).encode(), ctx("DS-SAT-04", scenario), area=AREA)


# --- DS-PORT-01 PortWatch -------------------------------------------------------------------------

# Tonnes moved per call by type (estimates; PortWatch's own estimates are model output too).
TONNES_PER_CALL = {
    "container": (9000, 2600),
    "tanker": (24000, 0),
    "dry_bulk": (32000, 0),
    "general_cargo": (11000, 400),
    "roro": (3000, 200),
}


def portwatch(
    result: DesResult, scenario: str, until: datetime, cyclone: dict[str, Any] | None = None
) -> list[Record]:
    """Daily calls by type (ocean-going only) and, in a disruption scenario, the event feature."""
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for v in result.visits:
        if v.kind != "lighter" and result.start <= v.arrive < until:
            per_day[v.arrive.date().isoformat()][v.kind] += 1
    features = []
    for day in sorted(per_day):
        counts = per_day[day]
        attrs: dict[str, Any] = {
            "date": day,
            "portid": "port241",
            "portname": "Chittagong",
            "ISO3": "BGD",
        }
        imp = exp = 0.0
        for kind, field_name in (
            ("container", "container"),
            ("tanker", "tanker"),
            ("dry_bulk", "dry_bulk"),
            ("general_cargo", "general_cargo"),
            ("roro", "roro"),
        ):
            n = counts.get(kind, 0)
            attrs[f"portcalls_{field_name}"] = n
            i, e = TONNES_PER_CALL[kind]
            attrs[f"import_{field_name}"] = n * i
            attrs[f"export_{field_name}"] = n * e
            imp, exp = imp + n * i, exp + n * e
        attrs |= {"portcalls": sum(counts.values()), "import": imp, "export": exp}
        features.append({"attributes": attrs})
    c = ctx("DS-PORT-01", scenario)
    out = parse_portwatch_daily(json.dumps({"features": features}).encode(), c)
    # The port list is real reference data (external ids): a twin never re-emits it.
    if cyclone:
        landfall = cyclone["landfall_ts"]
        feature = {
            "eventid": cyclone["event_id"],
            "eventtype": "TC",
            "eventname": cyclone["name"],
            "htmlname": f"Tropical Cyclone {cyclone['name']} (synthetic)",
            "htmldescription": (
                f"{cyclone['alert_level'].title()} synthetic cyclone affecting Chittagong"
            ),
            "alertlevel": cyclone["alert_level"].upper(),
            "country": "Bangladesh",
            "fromdate": int((landfall - timedelta(hours=36)).timestamp() * 1000),
            "todate": int((landfall + timedelta(hours=24)).timestamp() * 1000),
            "editdate": int(cyclone["alert_ts"].timestamp() * 1000),
            "affectedports": "port241",
            "lat": cyclone["landfall"]["lat"],
            "long": cyclone["landfall"]["lon"],
            "pageid": f"syn-{cyclone['event_id']}",
        }
        out += parse_portwatch_disruptions(
            json.dumps({"features": [{"attributes": feature}]}).encode(), c
        )
    return out


# --- DS-WX-01 Open-Meteo --------------------------------------------------------------------------


def _cyclone_factor(ts: datetime, cyclone: dict[str, Any] | None) -> float:
    """0 → 1 → 0 bell around landfall (standard deviation 14 h)."""
    if not cyclone:
        return 0.0
    hours = (ts - cyclone["landfall_ts"]).total_seconds() / 3600
    return math.exp(-0.5 * (hours / 14) ** 2)


def open_meteo(
    scenario: str,
    point_name: str,
    lat: float,
    lon: float,
    start: datetime,
    hours: int,
    marine: bool,
    issued: datetime,
    cyclone: dict[str, Any] | None = None,
    seed: int = 42,
) -> list[Record]:
    rng = random.Random(f"{seed}:wx:{point_name}:{marine}")
    times, cols = [], defaultdict(list)
    for h in range(hours):
        ts = start + timedelta(hours=h)
        local_hour = (ts.hour + 6) % 24
        f = _cyclone_factor(ts, cyclone)
        times.append(ts.strftime("%Y-%m-%dT%H:%M"))
        if marine:
            cols["wave_height"].append(round(0.6 + 0.3 * rng.random() + 5.5 * f, 2))
            cols["swell_wave_height"].append(round(0.5 + 0.2 * rng.random() + 3.0 * f, 2))
            cols["wave_period"].append(round(9 + 2 * rng.random() + 3 * f, 2))
            tide = 1.6 * math.cos(2 * math.pi * (h % 12.42) / 12.42)
            surge = (cyclone or {}).get("surge_m", 0.0) * f
            cols["sea_level_height_msl"].append(round(tide + surge, 2))
            cols["ocean_current_velocity"].append(round(1 + rng.random() + 4 * f, 1))
        else:
            cols["temperature_2m"].append(
                round(27 + 3 * math.sin((local_hour - 9) / 24 * 2 * math.pi) - 3 * f, 1)
            )
            cols["precipitation"].append(round(max(0.0, rng.gauss(0.1, 0.3)) + 28 * f, 1))
            wind = 12 + 6 * rng.random() + ((cyclone or {}).get("max_wind_kmh", 0) - 12) * f
            cols["wind_speed_10m"].append(round(wind, 1))
            cols["wind_gusts_10m"].append(round(wind * 1.45, 1))
            cols["wind_direction_10m"].append(int(150 + 60 * rng.random()) % 360)
            cols["pressure_msl"].append(
                round(1009 - (1009 - (cyclone or {}).get("min_pressure_hpa", 1009)) * f, 1)
            )
    units = {
        "temperature_2m": "°C", "precipitation": "mm", "wind_speed_10m": "km/h",
        "wind_gusts_10m": "km/h", "wind_direction_10m": "°", "pressure_msl": "hPa",
        "wave_height": "m", "swell_wave_height": "m", "wave_period": "s",
        "sea_level_height_msl": "m", "ocean_current_velocity": "km/h",
    }  # fmt: skip
    doc = {
        "latitude": lat,
        "longitude": lon,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": {"time": "iso8601", **{k: units[k] for k in cols}},
        "hourly": {"time": times, **cols},
    }
    c = ctx("DS-WX-01", scenario, fetched_at=issued)
    kind = WeatherKind.MARINE_FORECAST if marine else WeatherKind.FORECAST
    return parse_open_meteo(json.dumps(doc).encode(), c, point_name=point_name, kind=kind)


# --- DS-WX-02 GDACS -------------------------------------------------------------------------------


def gdacs(scenario: str, cyclone: dict[str, Any]) -> list[Record]:
    landfall = cyclone["landfall_ts"]
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [cyclone["landfall"]["lon"], cyclone["landfall"]["lat"]],
        },
        "properties": {
            "eventtype": "TC",
            "eventid": str(cyclone["event_id"]),
            "episodeid": "1",
            "eventname": cyclone["name"],
            "glide": "",
            "name": f"Tropical Cyclone {cyclone['name']} (synthetic)",
            "htmldescription": (
                f"{cyclone['alert_level'].title()} synthetic tropical cyclone {cyclone['name']}, "
                f"max wind {cyclone['max_wind_kmh']} km/h, landfall near Chattogram"
            ),
            "alertlevel": cyclone["alert_level"].title(),
            "iscurrent": "true",
            "country": "Bangladesh",
            "iso3": "BGD",
            "fromdate": (landfall - timedelta(hours=60)).strftime("%Y-%m-%dT%H:%M:%S"),
            "todate": (landfall + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
            "datemodified": cyclone["alert_ts"].strftime("%Y-%m-%dT%H:%M:%S"),
            "affectedcountries": [{"iso2": "BD", "iso3": "BGD", "countryname": "Bangladesh"}],
            "severitydata": {
                "severity": cyclone["max_wind_kmh"],
                "severitytext": f"{cyclone['max_wind_kmh']} km/h",
                "severityunit": "km/h",
            },
        },
    }
    return parse_gdacs(json.dumps(feature).encode(), ctx("DS-WX-02", scenario))


# --- News: DS-NEWS-01/02/03/04 --------------------------------------------------------------------


@dataclass(frozen=True)
class Story:
    published: datetime
    outlet: str  # fictional outlet on a reserved .example domain
    slug: str
    title: str
    snippet: str
    themes: tuple[str, ...]
    place: tuple[str, float, float]  # name, lat, lon

    @property
    def url(self) -> str:
        return f"https://{self.outlet}/{self.published:%Y/%m/%d}/{self.slug}"


def gdelt_doc(scenario: str, stories: list[Story]) -> list[Record]:
    doc = {
        "articles": [
            {
                "url": s.url,
                "url_mobile": "",
                "title": s.title,
                "seendate": s.published.strftime("%Y%m%dT%H%M%SZ"),
                "socialimage": "",
                "domain": s.outlet,
                "language": "English",
                "sourcecountry": "Bangladesh",
            }
            for s in stories
        ]
    }
    return parse_gdelt_doc(json.dumps(doc).encode(), ctx("DS-NEWS-01", scenario))


def gdelt_gkg(scenario: str, stories: list[Story]) -> list[Record]:
    rows = []
    for i, s in enumerate(stories):
        row = dict.fromkeys(GKG_COLUMNS, "")
        name, lat, lon = s.place
        row |= {
            "GKGRECORDID": f"{s.published:%Y%m%d%H%M%S}-SYN{i}",
            "DATE": s.published.strftime("%Y%m%d%H%M%S"),
            "SourceCollectionIdentifier": "1",
            "SourceCommonName": s.outlet,
            "DocumentIdentifier": s.url,
            "V2Themes": ";".join(f"{t},{10 * (j + 1)}" for j, t in enumerate(s.themes)),
            "V2Locations": f"4#{name}, Chittagong, Bangladesh#BG#BG84##{lat}#{lon}#-2#120",
            "V2Tone": "-4.2,1.1,5.3,6.4,22.0,0.5,310",
            "Extras": f"<PAGE_TITLE>{s.title}</PAGE_TITLE>",
        }
        rows.append("\t".join(row[c] for c in GKG_COLUMNS))
    return parse_gdelt_gkg(
        "\n".join(rows).encode(), ctx("DS-NEWS-02", scenario), columns=GKG_COLUMNS
    )


def rss(scenario: str, stories: list[Story], feed_id: str = "synthetic_wire") -> list[Record]:
    doc = {
        "feed": {"title": "Harbour Wire (synthetic)", "link": "https://harbourwire.example"},
        "items": [
            {
                "id": s.url,
                "link": s.url,
                "title": s.title,
                "published": s.published.isoformat(),
                "tags": list(s.themes[:3]),
                "snippet": s.snippet,
            }
            for s in stories
        ],
    }
    return parse_rss(json.dumps(doc).encode(), ctx("DS-NEWS-03", scenario), feed_id=feed_id)


def reliefweb(scenario: str, stories: list[Story], disaster: str) -> list[Record]:
    doc = {
        "data": [
            {
                "id": f"syn-{i}",
                "fields": {
                    "title": s.title,
                    "url_alias": s.url,
                    "date": {
                        "created": s.published.isoformat(),
                        "original": s.published.isoformat(),
                    },
                    "source": [{"shortname": "Synthetic OCHA"}],
                    "language": [{"code": "en"}],
                    "country": [{"iso3": "bgd"}],
                    "disaster_type": [{"name": "Tropical Cyclone"}],
                    "disaster": [{"name": disaster}],
                },
            }
            for i, s in enumerate(stories)
        ]
    }
    return parse_reliefweb_reports(json.dumps(doc).encode(), ctx("DS-NEWS-04", scenario))


# --- DS-PHARMA-01 openFDA -------------------------------------------------------------------------


def openfda_recall(
    scenario: str, firm: str, product: str, classification: str, when: datetime, seq: int = 1
) -> list[Record]:
    """A synthetic enforcement report for a FICTIONAL firm (pharma variant, 01 §5)."""
    doc = {
        "results": [
            {
                "recall_number": f"D-SYN-{when:%Y}-{seq:04d}",
                "event_id": f"SYN{seq:05d}",
                "status": "Ongoing",
                "classification": classification,
                "recalling_firm": firm,
                "product_description": product,
                "reason_for_recall": "CGMP deviations: synthetic scenario for demonstration only",
                "recall_initiation_date": when.strftime("%Y%m%d"),
                "report_date": (when + timedelta(days=7)).strftime("%Y%m%d"),
                "country": "India",
            }
        ]
    }
    return parse_openfda_recalls(json.dumps(doc).encode(), ctx("DS-PHARMA-01", scenario))
