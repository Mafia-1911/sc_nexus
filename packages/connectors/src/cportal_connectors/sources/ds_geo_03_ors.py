"""DS-GEO-03 · OpenRouteService (HGV profile): travel-time validation for the C3 graph."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://api.openrouteservice.org/v2/directions/driving-hgv"
# Chattogram port (UN/LOCODE BDCGP) to Dhaka Kamalapur ICD (Nominatim, DS-GEO-04), lon,lat.
START, END = "91.8333,22.3333", "90.4294,23.7337"


class OpenRouteService(Connector):
    ds_id = "DS-GEO-03"
    title = "OpenRouteService (HGV)"
    needs = ("ORS_API_KEY",)

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("no_key", API, "no_key", params={"start": START, "end": END}))
        if key := ctx.secret("ORS_API_KEY"):
            ctx.http(
                ProbeCall(
                    "ctg_to_kamalapur",
                    API,
                    sample=True,
                    params={"api_key": key, "start": START, "end": END},
                )
            )


CONNECTOR = OpenRouteService()
