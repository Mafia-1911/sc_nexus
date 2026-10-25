"""DS-PHARMA-02 · FDA Data Dashboard API: inspections, compliance actions, import refusals.

The API needs a free account (Authorization-User / Authorization-Key headers); without one the
probe records the failure mode and the docs page.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://api-datadashboard.fda.gov/v1"


class FdaDashboard(Connector):
    ds_id = "DS-PHARMA-02"
    title = "FDA Data Dashboard API"

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("docs", "https://datadashboard.fda.gov/oii/api/index.htm", "meta"))
        ctx.http(
            ProbeCall(
                "no_key",
                f"{API}/inspections_classifications",
                "no_key",
                method="POST",
                json_body={"start": 1, "rows": 1, "filters": {"CountryName": ["India"]}},
            )
        )


CONNECTOR = FdaDashboard()
