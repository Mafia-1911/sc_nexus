"""DS-AIS-03 · Danish Maritime Authority historical AIS (daily CSV zips)."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.landing import landing_and_files


class DanishAis(Connector):
    ds_id = "DS-AIS-03"
    title = "Danish Maritime Authority AIS"

    def probe(self, ctx: ProbeContext) -> None:
        files = landing_and_files(
            ctx, "listing", "http://aisdata.ais.dk/", r"aisdk.*\.zip$", max_files=0
        )
        if files:
            # The newest daily file only (sorted names end with the date).
            result = ctx.http(
                ProbeCall(
                    "latest_daily_head",
                    files[-1],
                    max_bytes=65_536,
                    note="first 64 KiB of the newest daily file",
                )
            )
            ctx.metric("latest_file", {"url": files[-1], "bytes": result.content_length})
            ctx.metric("files_listed", len(files))


CONNECTOR = DanishAis()
