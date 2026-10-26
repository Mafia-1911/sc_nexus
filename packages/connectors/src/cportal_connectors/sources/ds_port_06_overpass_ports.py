"""DS-PORT-06 · OSM via Overpass: port limits, anchorages, berths and terminals for geofences."""

from __future__ import annotations

from functools import partial

from cportal_core.areas import BBox, bbox
from cportal_core.schemas.records import PortZoneRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.overpass import (
    MIRROR,
    STATUS,
    element_counts,
    osm3s_timestamp,
    query_call,
    union,
)
from cportal_connectors.parsers.ports import parse_overpass_port_zones

MARITIME = [
    'nwr["seamark:type"~"^(anchorage|anchor_berth|harbour|mooring|berth|pilot_boarding|'
    'restricted_area|fairway)$"]',
    'nwr["harbour"]',
    'nwr["landuse"~"^(port|harbour)$"]',
    'nwr["industrial"~"^(port|container_terminal)$"]',
    'nwr["man_made"~"^(pier|quay|breakwater)$"]',
    'nwr["waterway"="dock"]',
]
TAG_KEYS = [
    "seamark:type",
    "harbour",
    "landuse",
    "industrial",
    "man_made",
    "waterway",
    "seamark:anchorage:category",
    "operator",
]


def _ctg_envelope() -> BBox:
    a, r = bbox("ctg_outer_anchorage"), bbox("ctg_port_river")
    return BBox(
        min(a.lon_min, r.lon_min),
        min(a.lat_min, r.lat_min),
        max(a.lon_max, r.lon_max),
        max(a.lat_max, r.lat_max),
    )


class OverpassPorts(Connector):
    ds_id = "DS-PORT-06"
    title = "OSM Overpass: port geometry"
    parsers = {
        "maritime_ctg.json": partial(parse_overpass_port_zones, locode="BDCGP"),
        "maritime_mongla.json": partial(parse_overpass_port_zones, locode="BDMGL"),
        "maritime_payra.json": partial(parse_overpass_port_zones, locode="BDPAY"),
    }
    record_types = (PortZoneRecord,)
    field_notes = {
        "maritime_ctg:id": FieldNote("", "OSM element ID; unique only together with type"),
        "maritime_ctg:center.lat": FieldNote("deg", "Centroid (ways/relations) from `out center`"),
        "maritime_ctg:tags.seamark:type": FieldNote("", "OpenSeaMap feature class"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("status", STATUS, "meta", note="slots available to this IP"))
        ctg = ctx.http(
            query_call(
                "maritime_ctg",
                union(MARITIME, _ctg_envelope()),
                sample=True,
                note="Chattogram outer anchorage + Karnaphuli river envelope",
            )
        )
        anchor = ctx.http(
            query_call(
                "anchorage_geometry_ctg",
                union(
                    ['nwr["seamark:type"~"^(anchorage|anchor_berth)$"]'],
                    _ctg_envelope(),
                    out="geom",
                ),
                sample=True,
                note="full geometry of anchorage features (are there polygons?)",
            )
        )
        mongla = ctx.http(
            query_call("maritime_mongla", union(MARITIME, bbox("mongla")), sample=True)
        )
        payra = ctx.http(query_call("maritime_payra", union(MARITIME, bbox("payra")), sample=True))
        ctx.http(
            query_call(
                "mirror_maritime_ctg",
                union(MARITIME, _ctg_envelope()),
                "meta",
                url=MIRROR,
                note="same query on the private.coffee mirror",
            )
        )
        ctx.http(query_call("syntax_error", "[out:json];nwr[seamark:type=(;out;", "bad_param"))
        ctx.http(
            query_call(
                "open_sea",
                union(MARITIME, BBox(88.5, 19.0, 88.6, 19.1)),
                "empty",
                note="0.1° box in the open Bay of Bengal",
            )
        )
        ctx.http(
            query_call("client_timeout", union(MARITIME, bbox("payra")), "timeout", timeout_s=0.001)
        )
        for name, result in (
            ("ctg", ctg),
            ("anchorage_ctg", anchor),
            ("mongla", mongla),
            ("payra", payra),
        ):
            element_counts(ctx, name, result.parsed, TAG_KEYS)
        ctx.metric("osm_base_timestamp", osm3s_timestamp(ctg.parsed))
        if isinstance(anchor.parsed, dict):
            ctx.metric(
                "anchorage_polygons",
                sum(
                    1
                    for el in anchor.parsed.get("elements", [])
                    if el.get("type") in ("way", "relation")
                ),
            )


CONNECTOR = OverpassPorts()
