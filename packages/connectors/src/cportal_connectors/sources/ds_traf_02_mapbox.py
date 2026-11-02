"""DS-TRAF-02 · Mapbox traffic (U-07): live congestion where TomTom has none (A-103).

Probe first (D-08): traffic-aware routing with per-segment congestion ("unknown" = no data) on
Chattogram → Gazipur and inside Dhaka (Jatrabari → Tongi), and one traffic vector tile over
Dhaka (mapbox-traffic-v1; an empty tile means no live lines there).
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

DIRECTIONS = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords}"
TILE = "https://api.mapbox.com/v4/mapbox.mapbox-traffic-v1/{z}/{x}/{y}.vector.pbf"
ROUTES = {
    "ctg_to_gazipur": "91.8333,22.3333;90.4203,23.9999",
    "dhaka_jatrabari_to_tongi": "90.4336,23.7104;90.4023,23.8915",
}


class MapboxTraffic(Connector):
    ds_id = "DS-TRAF-02"
    title = "Mapbox traffic"
    needs = ("MAPBOX_TOKEN",)

    def probe(self, ctx: ProbeContext) -> None:
        token = ctx.secret("MAPBOX_TOKEN")
        if not token:
            ctx.note("no MAPBOX_TOKEN: nothing to probe")
            return
        for name, coords in ROUTES.items():
            ctx.http(
                ProbeCall(
                    f"route_{name}",
                    DIRECTIONS.format(coords=coords),
                    sample=True,
                    params={
                        "access_token": token,
                        "annotations": "congestion,speed,duration",
                        "overview": "full",
                        "geometries": "geojson",
                    },
                )
            )
        # Dhaka at zoom 12: x = 3076, y = 1770.
        ctx.http(ProbeCall("tile_dhaka_z12", TILE.format(z=12, x=3076, y=1770),
                           params={"access_token": token}))  # fmt: skip


CONNECTOR = MapboxTraffic()
