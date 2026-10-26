"""DS-PORT-08 · searoute: offline sea-lane distances on the Eurostat MARNET network."""

from __future__ import annotations

import importlib.metadata as md
import json
import time
from typing import Any

import searoute
from cportal_core.schemas.records import LaneRecord, LocationRecord

from cportal_connectors.base import Connector, FieldNote
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.ports import parse_searoute_routes

# Origin is the UN/LOCODE BDCGP coordinate (2220N 09150E, probed in DS-PORT-05). Destinations are
# approximate public port positions, used only to exercise the network and record distances.
ORIGIN = ("BDCGP", (91.8333, 22.3333))
DESTINATIONS = {
    "LKCMB Colombo": (79.85, 6.95),
    "SGSIN Singapore": (103.85, 1.26),
    "MYPKG Port Klang": (101.39, 3.0),
    "BDMGL Mongla (sea approach)": (89.6, 22.48),
    "NLRTM Rotterdam": (4.05, 51.95),
    "USLAX Los Angeles": (-118.27, 33.73),
}


class Searoute(Connector):
    ds_id = "DS-PORT-08"
    title = "searoute (Eurostat MARNET sea lanes)"
    parsers = {"routes.json": parse_searoute_routes}
    record_types = (LocationRecord, LaneRecord)
    field_notes = {
        "routes:properties.length": FieldNote("nautical miles", "Route length on MARNET"),
        "routes:properties.duration_hours": FieldNote("h", "At the package's default speed"),
        "routes:geometry.coordinates": FieldNote("[lon, lat]", "LineString vertices"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        dist = md.distribution("searoute")
        meta = {
            "version": dist.version,
            "license": dist.metadata.get("License"),
            "license_expression": dist.metadata.get("License-Expression"),
            "classifiers": [c for c in dist.metadata.get_all("Classifier") or [] if "License" in c],
            "home_page": dist.metadata.get("Home-page"),
            "project_urls": dist.metadata.get_all("Project-URL"),
        }
        ctx.metric("package", meta)
        features: list[dict[str, Any]] = []
        timings = {}
        for label, dest in DESTINATIONS.items():
            start = time.perf_counter()
            route = searoute.searoute(
                list(ORIGIN[1]), list(dest), units="naut", append_orig_dest=True
            )
            timings[label] = round((time.perf_counter() - start) * 1000, 1)
            feature = dict(route)
            feature["properties"] = {**route["properties"], "to": label, "from": ORIGIN[0]}
            features.append(feature)
        collection = {"type": "FeatureCollection", "features": features}
        ctx.record_local(
            "routes",
            request={
                "url": "searoute.searoute()",
                "origin": ORIGIN,
                "destinations": DESTINATIONS,
                "units": "naut",
            },
            body=json.dumps(collection).encode(),
            ext="json",
            content_type="application/geo+json",
            records="features[]",
            sample=True,
            latency_ms=sum(timings.values()),
        )
        ctx.metric(
            "route_nm",
            {f["properties"]["to"]: round(f["properties"]["length"], 1) for f in features},
        )
        ctx.metric(
            "route_vertices",
            {f["properties"]["to"]: len(f["geometry"]["coordinates"]) for f in features},
        )
        ctx.metric("compute_ms", timings)
        first = features[0]["geometry"]["coordinates"]
        ctx.metric("first_vertices_from_origin", first[:3])


CONNECTOR = Searoute()
