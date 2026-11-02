"""DS-VSL-01 · DataDocked vessel management (U-07): a ship's owner, manager and P&I insurer.

A paid API on a 20-credit trial (D-07 exception, user decision U-07); the management lookup costs
3 credits, so the probe spends exactly one call, on a real ship GFW saw at Chattogram (DING
HENG 50, MMSI 412428640, 23 Oct 2026), and the app caches every answer: P&I cover renews yearly.
Auth: `x-api-key` header (docs.datadocked.com).
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

MANAGEMENT = "https://datadocked.com/api/vessels_operations/get-vessel-management-data"
PROBE_SHIP = "412428640"


class DataDocked(Connector):
    ds_id = "DS-VSL-01"
    title = "DataDocked vessel management (P&I)"
    needs = ("DATADOCKED_API_KEY",)

    def probe(self, ctx: ProbeContext) -> None:
        key = ctx.secret("DATADOCKED_API_KEY")
        if not key:
            ctx.note("no DATADOCKED_API_KEY: nothing to probe")
            return
        ctx.note("one call (3 trial credits)")
        ctx.http(
            ProbeCall(
                "management_ding_heng_50",
                MANAGEMENT,
                sample=True,
                params={"imo_or_mmsi": PROBE_SHIP},
                headers={"x-api-key": key, "accept": "application/json"},
            )
        )


CONNECTOR = DataDocked()
