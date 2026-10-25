"""DS-GEO-01 · Geofabrik Bangladesh OSM extract (roads, rail, waterways for the C3 graph)."""

from __future__ import annotations

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext

BASE = "https://download.geofabrik.de/asia"


class Geofabrik(Connector):
    ds_id = "DS-GEO-01"
    title = "Geofabrik Bangladesh extract"
    field_notes = {
        "state:sequenceNumber": FieldNote("", "Replication sequence of the diff stream"),
        "state:timestamp": FieldNote("ISO 8601 (escaped colons)", "Data cut-off of the extract"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        page = ctx.http(
            ProbeCall("index_page", f"{BASE}/bangladesh.html", "meta", decode=html_outline)
        )
        # First 64 KiB only: enough to read Content-Length and the PBF header block.
        pbf = ctx.http(
            ProbeCall(
                "pbf_head",
                f"{BASE}/bangladesh-latest.osm.pbf",
                max_bytes=65_536,
                ext="pbf",
                note="partial read; full file is fetched in M5 (C3)",
            )
        )
        ctx.http(ProbeCall("pbf_md5", f"{BASE}/bangladesh-latest.osm.pbf.md5", "meta"))
        ctx.http(
            ProbeCall(
                "state",
                f"{BASE}/bangladesh-updates/state.txt",
                sample=True,
                decode=lambda b: dict(
                    line.split("=", 1)
                    for line in b.decode().splitlines()
                    if "=" in line and not line.startswith("#")
                ),
                note="replication state: data cut-off and sequence",
            )
        )
        ctx.http(
            ProbeCall(
                "poly",
                f"{BASE}/bangladesh.poly",
                sample=True,
                note="boundary polygon (Osmosis .poly)",
            )
        )
        mbtiles = ctx.http(
            ProbeCall(
                "shortbread_mbtiles_head",
                f"{BASE}/bangladesh-shortbread-1.0.mbtiles",
                "meta",
                max_bytes=1024,
                ext="mbtiles",
                note="vector-tile package; size tells whether an offline basemap is practical",
            )
        )
        ctx.http(
            ProbeCall(
                "missing_region",
                f"{BASE}/bangladesh-nope-latest.osm.pbf",
                "bad_param",
                max_bytes=1024,
            )
        )
        ctx.http(ProbeCall("client_timeout", f"{BASE}/bangladesh.poly", "timeout", timeout_s=0.001))
        ctx.metric("pbf_bytes", pbf.content_length)
        ctx.metric("shortbread_mbtiles_bytes", mbtiles.content_length)
        if isinstance(page.parsed, dict):
            ctx.metric(
                "files_listed",
                sorted(
                    {link["href"] for link in page.parsed["links"] if "bangladesh" in link["href"]}
                )[:30],
            )


CONNECTOR = Geofabrik()
