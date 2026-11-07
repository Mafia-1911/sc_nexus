"""DS-PORT-10 · Chittagong Port Authority public TOS dashboard + PCS (cpatos.gov.bd).

Probe: the PCS vessel schedule and the container vessels at berth (two polite calls). Live
polling is not the generic connector loop: the worker's `cpa:*` jobs (cpa_cli) fetch all the
public reports on their own schedules and store them (cpa_store). Checks: the committed samples
still parse into visits and berth rows, so a change in CPA's page layout fails loudly.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.cpa_tos import BASE, PAGES, parse_at_berth, parse_pcs
from cportal_connectors.harness import ProbeContext


def check_pcs(body: bytes) -> int:
    visits = parse_pcs(body.decode("utf-8", "replace"))
    if not visits or not all(v["visit_ref"] and v["phase"] for v in visits):
        raise ValueError("PCS schedule: no visits parsed (page layout changed?)")
    return len(visits)


def check_at_berth(body: bytes) -> int:
    rows = parse_at_berth(body.decode("utf-8", "replace"))
    if not rows or not all(r["vessel"] for r in rows):
        raise ValueError("vessels at berth: no rows parsed (page layout changed?)")
    return len(rows)


class CpaTos(Connector):
    ds_id = "DS-PORT-10"
    title = "CPA public TOS dashboard + PCS"
    checks = {"pcs_schedule.html": check_pcs, "vessels_at_berth.html": check_at_berth}

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("pcs_schedule", BASE + PAGES["pcs"], sample=True))
        ctx.http(ProbeCall("vessels_at_berth", BASE + PAGES["at_berth_container"], sample=True))


CONNECTOR = CpaTos()
