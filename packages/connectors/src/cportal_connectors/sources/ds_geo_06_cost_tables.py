"""DS-GEO-06 · Bangladesh cost tables (diesel, tolls, rail and barge tariffs): a manual table.

Each value gets a source URL and date in config (M5). The probe only checks that the official
pages are reachable.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

PAGES = {
    "bpc_home": "https://bpc.gov.bd/",
    "bangladesh_railway": "https://railway.gov.bd/",
    "biwtc_home": "https://biwtc.gov.bd/",
}


class CostTables(Connector):
    ds_id = "DS-GEO-06"
    title = "Bangladesh cost tables (manual)"

    def probe(self, ctx: ProbeContext) -> None:
        for name, url in PAGES.items():
            ctx.http(ProbeCall(name, url, "meta", timeout_s=60))


CONNECTOR = CostTables()
