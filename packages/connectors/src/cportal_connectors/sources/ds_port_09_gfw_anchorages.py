"""DS-PORT-09 · GFW named anchorages. The downloadable table needs a GFW website login; the
same anchorage IDs and positions already arrive inside port-visit events (DS-AIS-02).
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext


class GfwAnchorages(Connector):
    ds_id = "DS-PORT-09"
    title = "GFW named anchorages"

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "datasets_page",
                "https://globalfishingwatch.org/datasets-and-code-anchorages/",
                "meta",
                note="landing page of the anchorage dataset",
            )
        )


CONNECTOR = GfwAnchorages()
