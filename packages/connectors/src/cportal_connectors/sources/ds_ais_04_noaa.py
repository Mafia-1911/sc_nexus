"""DS-AIS-04 · NOAA MarineCadastre AIS (US waters): daily files for pretraining and backtests."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.landing import landing_and_files


class NoaaAis(Connector):
    ds_id = "DS-AIS-04"
    title = "NOAA MarineCadastre AIS"

    def probe(self, ctx: ProbeContext) -> None:
        repo = ctx.http(
            ProbeCall(
                "github_repo",
                "https://api.github.com/repos/ocm-marinecadastre/ais-vessel-traffic",
                "meta",
            )
        )
        if isinstance(repo.parsed, dict):
            ctx.metric(
                "repo", {k: repo.parsed.get(k) for k in ("pushed_at", "license", "description")}
            )
        landing_and_files(
            ctx,
            "handler_2025",
            "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2025/index.html",
            r"\.(zip|parquet)$",
            max_files=1,
        )


CONNECTOR = NoaaAis()
