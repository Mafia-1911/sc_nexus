"""DS-PORT-04 · World Port Index (NGA Pub 150): port attributes and coordinates."""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://msi.nga.mil/api/publications/world-port-index"


class WorldPortIndex(Connector):
    ds_id = "DS-PORT-04"
    title = "World Port Index (NGA Pub 150)"

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("publication_page", "https://msi.nga.mil/Publications/WPI", "meta"))
        ports = ctx.http(
            ProbeCall(
                "wpi_all_json",
                API,
                params={"output": "json"},
                max_bytes=40_000_000,
                timeout_s=120,
                note="whole index as JSON (filtered to Bangladesh below)",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_output", API, "bad_param", params={"output": "xml-nope"}, max_bytes=65_536
            )
        )
        rows = self._rows(ports.parsed)
        ctx.metric("ports_total", len(rows))
        if rows:
            ctx.metric("columns", sorted(rows[0])[:80])
            bd = [
                r
                for r in rows
                if "bangladesh" in str(r.get("countryName", "")).lower()
                or str(r.get("countryCode", "")).upper() in ("BD", "BGD")
            ]
            ctx.metric(
                "bangladesh_ports",
                [
                    {
                        k: r.get(k)
                        for k in (
                            "portNumber",
                            "portName",
                            "unloCode",
                            "ycoord",
                            "xcoord",
                            "harborSize",
                            "harborType",
                            "chDepth",
                            "maxVesselLength",
                        )
                    }
                    for r in bd
                ],
            )

    @staticmethod
    def _rows(doc: Any) -> list[dict[str, Any]]:
        if isinstance(doc, dict):
            for key in ("ports", "data", "features"):
                if isinstance(doc.get(key), list):
                    return [r for r in doc[key] if isinstance(r, dict)]
        return doc if isinstance(doc, list) else []


CONNECTOR = WorldPortIndex()
