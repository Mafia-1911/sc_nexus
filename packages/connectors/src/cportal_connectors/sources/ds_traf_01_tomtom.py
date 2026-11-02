"""DS-TRAF-01 · TomTom Traffic (U-07): live flow on the corridor and traffic-aware truck routing.

Probe first (D-08): does TomTom have live flow data in Bangladesh at all? Four points on the
corridor (Dhaka's N1 entry, Chattogram port road, the N1 at Cumilla, Tongi on the Gazipur road),
one truck route Chattogram → Gazipur with live and no-traffic times, and one flow tile over
Dhaka (the map layer, proxied by the API so the key never reaches a browser).
Free tier: about 2,500 non-tile and 50,000 tile requests a day.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

FLOW = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
ROUTE = "https://api.tomtom.com/routing/1/calculateRoute/{a}:{b}/json"
TILE = "https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png"
POINTS = {
    "dhaka_n1_jatrabari": "23.7104,90.4336",
    "ctg_port_road": "22.3076,91.7993",
    "n1_cumilla": "23.4607,91.1809",
    "tongi_gazipur_road": "23.8915,90.4023",
}
CTG, GAZIPUR = "22.3333,91.8333", "23.9999,90.4203"


class TomTomTraffic(Connector):
    ds_id = "DS-TRAF-01"
    title = "TomTom Traffic"
    needs = ("TOMTOM_API_KEY",)

    def probe(self, ctx: ProbeContext) -> None:
        key = ctx.secret("TOMTOM_API_KEY")
        if not key:
            ctx.note("no TOMTOM_API_KEY: nothing to probe")
            return
        for name, point in POINTS.items():
            ctx.http(
                ProbeCall(
                    f"flow_{name}", FLOW, sample=True,
                    params={"point": point, "unit": "KMPH", "key": key},
                )
            )  # fmt: skip
        ctx.http(
            ProbeCall(
                "route_ctg_gazipur_truck",
                ROUTE.format(a=CTG, b=GAZIPUR),
                sample=True,
                params={
                    "traffic": "true",
                    "travelMode": "truck",
                    "computeTravelTimeFor": "all",
                    "key": key,
                },
            )
        )
        ctx.http(ProbeCall("tile_dhaka_z10", TILE.format(z=10, x=769, y=442), params={"key": key}))


CONNECTOR = TomTomTraffic()
