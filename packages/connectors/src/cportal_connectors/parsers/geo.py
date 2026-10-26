"""Geo reference data: Geofabrik extract boundary, OSM inland sites, GeoNames, DESNZ emission
factors, World Bank indicators, and the basemap style check."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from cportal_core.enums import LocationKind, TransportMode
from cportal_core.schemas.records import (
    CountryIndicatorRecord,
    EmissionFactorRecord,
    LocationRecord,
    Record,
    point,
)

from cportal_connectors.canonical import ParseContext
from cportal_connectors.parsers.ports import _osm_point

# --- Geofabrik (DS-GEO-01) ----------------------------------------------------------------------


def parse_osmosis_poly(body: bytes, ctx: ParseContext) -> list[Record]:
    """Osmosis .poly (the extract boundary) → one region with a MultiPolygon. Rings whose name
    starts with '!' are holes of the preceding ring."""
    lines = [line.strip() for line in body.decode("utf-8").splitlines()]
    polygons: list[list[list[list[float]]]] = []
    ring: list[list[float]] | None = None
    hole = False
    for line in lines[1:]:
        if line == "END":
            if ring is None:
                break  # end of file
            closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
            if hole and polygons:
                polygons[-1].append(closed)
            else:
                polygons.append([closed])
            ring = None
        elif ring is None:
            ring, hole = [], line.startswith("!")
        elif line:
            lon, lat = (float(x) for x in line.split()[:2])
            ring.append([lon, lat])
    return [
        LocationRecord(
            id=ctx.rid("location", "geofabrik:bangladesh"),
            **ctx.lineage("geofabrik:asia/bangladesh"),
            name="Bangladesh (Geofabrik extract boundary)",
            country_iso2="BD",
            kind=LocationKind.REGION,
            geom_area={"type": "MultiPolygon", "coordinates": polygons},
            attrs={"extract": "asia/bangladesh"},
        )
    ]


# --- Overpass inland sites (DS-GEO-02) -----------------------------------------------------------

# Overpass name regexes for "ICD" also catch icddr,b clinics and ICDS offices (PROBE_REPORT S11);
# keep logistics sites only.
_LOGISTICS = re.compile(r"(?i)container|off-dock|\bicd\b|inland container|depot|\bcfs\b")
_NOT_LOGISTICS = re.compile(
    r"(?i)icddr|icdp|icds|nicdu|masjid|mosque|fire station|bus stop|road|college|club|clinic|"
    r"hospital|centre|center|social welfare|office"
)


def parse_overpass_sites(body: bytes, ctx: ParseContext, kind: LocationKind) -> list[Record]:
    out: list[Record] = []
    for element in json.loads(body).get("elements", []):
        tags = element.get("tags") or {}
        name = tags.get("name") or tags.get("name:en")
        where = _osm_point(element)
        if not name or where is None:
            continue
        if kind in (LocationKind.ICD, LocationKind.DEPOT) and (
            not _LOGISTICS.search(name) or _NOT_LOGISTICS.search(name)
        ):
            continue
        osm_ref = f"{element['type']}/{element['id']}"
        out.append(
            LocationRecord(
                id=ctx.rid("location", osm_ref),
                **ctx.lineage(osm_ref),
                name=name[:200],
                name_bn=tags.get("name:bn"),
                country_iso2="BD",
                kind=kind,
                geom=point(*where),
                attrs={
                    "osm": osm_ref,
                    "tags": {k: v for k, v in tags.items() if not k.startswith("name")},
                },
            )
        )
    return out


# --- GeoNames (DS-GEO-04) -------------------------------------------------------------------------

GEONAMES_KIND = {
    "P": LocationKind.CITY,
    "A": LocationKind.REGION,
    "S": LocationKind.SITE,
    "L": LocationKind.OTHER,
}


def parse_geonames_tsv(body: bytes, ctx: ParseContext) -> list[Record]:
    """The gazetteer for C2 geocoding. Nominatim responses are a lookup cache, not reference
    data, so they are not loaded (one probe hit was a college for "Chattogram port")."""
    out: list[Record] = []
    for row in csv.DictReader(io.StringIO(body.decode("utf-8")), delimiter="\t"):
        feature_class, code = row["feature_class"], row["feature_code"]
        kind = GEONAMES_KIND.get(feature_class, LocationKind.OTHER)
        if code == "PRT":
            kind = LocationKind.SEAPORT
        elif code == "RSTN":
            kind = LocationKind.RAIL_HUB
        out.append(
            LocationRecord(
                id=ctx.rid("location", f"geonames:{row['geonameid']}"),
                **ctx.lineage(row["geonameid"]),
                geonames_id=int(row["geonameid"]),
                name=row["name"],
                country_iso2=row["country_code"] or None,
                kind=kind,
                geom=point(float(row["longitude"]), float(row["latitude"])),
                attrs={
                    "feature": f"{feature_class}.{code}",
                    "admin1": row.get("admin1_code") or None,
                    "population": int(row["population"] or 0) or None,
                    "alternatenames": (row.get("alternatenames") or "")[:500] or None,
                },
            )
        )
    return out


# --- UK DESNZ emission factors (DS-GEO-05) ------------------------------------------------------

DESNZ_MODE = {
    "Vans": TransportMode.ROAD,
    "HGV (all diesel)": TransportMode.ROAD,
    "HGV (non-refrigerated, all diesel)": TransportMode.ROAD,
    "HGV (refrigerated, all diesel)": TransportMode.ROAD,
    "HGVs refrigerated": TransportMode.ROAD,
    "Freight flights": TransportMode.AIR,
    "Rail": TransportMode.RAIL,
    "Sea tanker": TransportMode.SEA,
    "Cargo ship": TransportMode.SEA,
}


def parse_desnz_flat(body: bytes, ctx: ParseContext) -> list[Record]:
    """Freight factors per tonne-km in kg CO2e (totals only; the gas split rows are skipped).
    'Freighting goods' rows are tank-to-wheel; 'WTT- …' rows are well-to-tank (A-016)."""
    out: list[Record] = []
    for row in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
        level1, level2 = row["Level 1"], row["Level 2"]
        if row["UOM"] != "tonne.km" or row["GHG/Unit"] != "kg CO2e":
            continue
        if level1 == "Freighting goods":
            scope = "TTW"
        elif level1.startswith("WTT"):
            scope = "WTT"
        else:
            continue
        mode = DESNZ_MODE.get(level2.strip()) or next(
            (m for k, m in DESNZ_MODE.items() if level2.startswith(k.split(" (")[0])), None
        )
        value_text = row.get("GHG Conversion Factor 2026") or ""
        if mode is None or not value_text.strip():
            continue
        vehicle = " / ".join(
            x.strip() for x in (level2, row["Level 3"], row["Level 4"]) if x.strip()
        )
        out.append(
            EmissionFactorRecord(
                id=ctx.rid("emission_factor", row["ID"]),
                **ctx.lineage(row["ID"]),
                mode=mode,
                vehicle_class=vehicle[:200],
                fuel=(row.get("Column Text") or "").strip() or None,
                unit="tonne.km",
                ghg_unit="kg CO2e",
                value=float(value_text),
                scope=scope,
                year=2026,
            )
        )
    return out


# --- World Bank indicators (DS-TRADE-03) ---------------------------------------------------------


def parse_worldbank_indicators(body: bytes, ctx: ParseContext) -> list[Record]:
    """`[page_info, rows]`; rows without a value are skipped (missing years, not zeros)."""
    doc = json.loads(body)
    rows = doc[1] if isinstance(doc, list) and len(doc) > 1 else []
    out: list[Record] = []
    for r in rows or []:
        if r.get("value") is None or not str(r.get("date", "")).isdigit():
            continue
        code, iso3, year = r["indicator"]["id"], r["countryiso3code"], int(r["date"])
        out.append(
            CountryIndicatorRecord(
                id=ctx.rid("country_indicator", f"{iso3}:{code}:{year}"),
                **ctx.lineage(f"{iso3}:{code}:{year}"),
                country_iso3=iso3,
                indicator_code=code,
                indicator_name=r["indicator"]["value"][:300],
                year=year,
                value=float(r["value"]),
                unit=r.get("unit") or None,
            )
        )
    return out


# --- Basemap (DS-GEO-07) --------------------------------------------------------------------------


def check_tilejson(body: bytes) -> dict[str, Any]:
    """No canonical rows: the basemap contract is a usable TileJSON 3 with attribution."""
    doc: dict[str, Any] = json.loads(body)
    if not str(doc.get("tilejson", "")).startswith("3"):
        raise ValueError("not TileJSON 3")
    tiles = doc.get("tiles") or []
    if not tiles or not all("{z}" in t and "{x}" in t and "{y}" in t for t in tiles):
        raise ValueError("tile URL templates missing {z}/{x}/{y}")
    if not doc.get("attribution"):
        raise ValueError("attribution missing (required by the tile licence)")
    return doc


def check_style(body: bytes) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(body)
    if doc.get("version") != 8 or not doc.get("sources") or not doc.get("layers"):
        raise ValueError("not a MapLibre style v8 with sources and layers")
    return doc
