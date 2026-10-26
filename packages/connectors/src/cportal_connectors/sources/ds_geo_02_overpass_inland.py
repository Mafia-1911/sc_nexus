"""DS-GEO-02 · OSM via Overpass: ICDs, depots, river terminals, EPZs, tolls and bridges.

Country-wide name regexes take 1-2 minutes on the overloaded main instance, so the river, rail
and bridge queries are scoped to the Dhaka region or the Dhaka–Chattogram corridor.
"""

from __future__ import annotations

from functools import partial

from cportal_core.areas import bbox
from cportal_core.enums import LocationKind
from cportal_core.schemas.records import LocationRecord

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
from cportal_connectors.parsers.geo import parse_overpass_sites

TAG_KEYS = [
    "landuse",
    "industrial",
    "railway",
    "amenity",
    "barrier",
    "harbour",
    "operator",
    "man_made",
    "building",
]


class OverpassInland(Connector):
    ds_id = "DS-GEO-02"
    title = "OSM Overpass: inland logistics infrastructure"
    parsers = {
        "container_sites_bd.json": partial(parse_overpass_sites, kind=LocationKind.DEPOT),
        "epz_bd.json": partial(parse_overpass_sites, kind=LocationKind.EPZ),
        "rail_hubs_corridor.json": partial(parse_overpass_sites, kind=LocationKind.RAIL_HUB),
        "toll_booths_bd.json": partial(parse_overpass_sites, kind=LocationKind.TOLL_POINT),
    }
    record_types = (LocationRecord,)
    field_notes = {
        "container_sites_bd:tags.name": FieldNote("", "Free-text name; ICD naming is inconsistent"),
        "container_sites_bd:center.lon": FieldNote("deg", "Centroid of ways/relations"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        bd, dhaka, corridor = bbox("bangladesh"), bbox("dhaka_region"), bbox("dhaka_ctg_corridor")
        ctx.http(ProbeCall("status", STATUS, "meta"))
        containers = ctx.http(
            query_call(
                "container_sites_bd",
                union(
                    [
                        'nwr["name"~"(ICD|Inland Container|Container Depot|Container Terminal|'
                        'Container Yard|Off-?Dock)",i]'
                    ],
                    bd,
                ),
                sample=True,
                note="ICDs and off-dock container depots by name, whole country",
            )
        )
        river = ctx.http(
            query_call(
                "river_terminals_dhaka",
                union(
                    [
                        'nwr["harbour"]',
                        'nwr["amenity"="ferry_terminal"]',
                        'nwr["landuse"="port"]',
                        'nwr["name"~"Pangaon",i]',
                    ],
                    dhaka,
                ),
                sample=True,
                note="river ports, ferry terminals, Pangaon ICT (Dhaka region)",
            )
        )
        epz = ctx.http(
            query_call(
                "epz_bd",
                union(['nwr["name"~"(Export Processing Zone|EPZ|Economic Zone)",i]'], bd),
                sample=True,
                note="EPZs and economic zones (garment and pharma clusters)",
            )
        )
        tolls = ctx.http(
            query_call("toll_booths_bd", union(['nwr["barrier"="toll_booth"]'], bd), sample=True)
        )
        rail = ctx.http(
            query_call(
                "rail_hubs_corridor",
                union(['nwr["railway"~"^(station|yard)$"]'], corridor),
                sample=True,
                note="stations and yards on the corridor (Kamalapur ICD rail link)",
            )
        )
        ctx.http(
            query_call(
                "bridges_count_corridor",
                union(
                    ['way["bridge"="yes"]["highway"~"^(motorway|trunk|primary)$"]'],
                    corridor,
                    out="count",
                ),
                note="major-road bridge segments on the corridor (count only)",
            )
        )
        ctx.http(
            query_call(
                "mirror_container_sites_bd",
                union(
                    [
                        'nwr["name"~"(ICD|Inland Container|Container Depot|Container Terminal|'
                        'Container Yard|Off-?Dock)",i]'
                    ],
                    bd,
                ),
                "meta",
                url=MIRROR,
                note="same query on the private.coffee mirror",
            )
        )
        ctx.http(query_call("syntax_error", '[out:json];nwr["name"~"(";out;', "bad_param"))
        for name, result in (
            ("container_sites", containers),
            ("river_terminals", river),
            ("epz", epz),
            ("toll_booths", tolls),
            ("rail_hubs", rail),
        ):
            element_counts(ctx, name, result.parsed, TAG_KEYS)
        ctx.metric("osm_base_timestamp", osm3s_timestamp(containers.parsed))


CONNECTOR = OverpassInland()
