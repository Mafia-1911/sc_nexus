"""DS-GEO-07 · Basemap tiles: OpenFreeMap (no key) and Protomaps builds."""

from __future__ import annotations

import math
from typing import Any

from cportal_core.areas import bbox

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.geo import check_style, check_tilejson

OFM = "https://tiles.openfreemap.org"
PROTOMAPS_BUILDS = "https://build-metadata.protomaps.dev/builds.json"


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


class Basemap(Connector):
    ds_id = "DS-GEO-07"
    title = "Basemap tiles (OpenFreeMap, Protomaps)"
    # No canonical rows: the contract is a usable TileJSON and MapLibre style.
    checks = {"tilejson.json": check_tilejson, "style_liberty.json": check_style}
    field_notes = {
        "style_liberty:sources.openmaptiles.url": FieldNote("", "TileJSON URL the style uses"),
        "tilejson:tiles": FieldNote("", "Tile URL template; includes a dated build path"),
        "tilejson:maxzoom": FieldNote("zoom", "Highest zoom with data"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "style_liberty", f"{OFM}/styles/liberty", sample=True, note="MapLibre style JSON"
            )
        )
        tilejson = ctx.http(ProbeCall("tilejson", f"{OFM}/planet", sample=True))
        template = self._template(tilejson.parsed)
        lon, lat = bbox("ctg_port_river").center()
        if template:
            for z in (8, 12, 14):
                x, y = tile_xy(lon, lat, z)
                ctx.http(
                    ProbeCall(
                        f"tile_z{z}",
                        template.format(z=z, x=x, y=y),
                        ext="pbf",
                        note=f"vector tile over the Karnaphuli berths ({x},{y})",
                    )
                )
            ctx.http(
                ProbeCall(
                    "tile_beyond_maxzoom", template.format(z=20, x=0, y=0), "bad_param", ext="pbf"
                )
            )
        ctx.http(
            ProbeCall(
                "protomaps_builds",
                PROTOMAPS_BUILDS,
                "meta",
                note="daily planet PMTiles builds (self-host / extract option)",
            )
        )
        ctx.http(ProbeCall("client_timeout", f"{OFM}/planet", "timeout", timeout_s=0.001))
        if isinstance(tilejson.parsed, dict):
            ctx.metric(
                "tilejson",
                {
                    k: tilejson.parsed.get(k)
                    for k in ("tiles", "minzoom", "maxzoom", "attribution", "version")
                },
            )

    @staticmethod
    def _template(doc: Any) -> str | None:
        if isinstance(doc, dict) and doc.get("tiles"):
            return str(doc["tiles"][0])
        return None


CONNECTOR = Basemap()
