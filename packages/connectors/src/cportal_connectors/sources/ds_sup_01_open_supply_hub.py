"""DS-SUP-01 · Open Supply Hub: real garment facility locations (account download, ≤ 5,000 rows).

The API is paid (excluded, 03 §2.10). This probe only checks the public pages; the download
itself needs a free account and a human click.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext


class OpenSupplyHub(Connector):
    ds_id = "DS-SUP-01"
    title = "Open Supply Hub"

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("home", "https://opensupplyhub.org/", "meta"))
        ctx.http(ProbeCall("robots", "https://opensupplyhub.org/robots.txt", "meta"))
        ctx.http(
            ProbeCall(
                "api_no_key",
                "https://opensupplyhub.org/api/facilities/",
                "no_key",
                params={"countries": "BD", "pageSize": 1},
                note="paid API: expect 401/403 without a token; not used",
            )
        )


CONNECTOR = OpenSupplyHub()
