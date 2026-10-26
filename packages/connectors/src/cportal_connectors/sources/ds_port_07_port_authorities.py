"""DS-PORT-07 · Chittagong and Mongla Port Authority websites: what is public, and may we read it?

Manual-first: robots.txt and the home pages only. Any schedule page found is listed for a human
decision before a connector touches it.
"""

from __future__ import annotations

import re

from cportal_core.schemas.records import (
    PortCallRecord,
    PortStateSnapshotRecord,
    PortZoneRecord,
    VesselRecord,
)

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.cpa import parse_cpa_berthing

SITES = {"cpa": "https://cpa.gov.bd", "mpa": "https://mpa.gov.bd"}
INTERESTING = re.compile(
    r"(?i)vessel|berth|schedule|anchorage|shipping|container|arrival|"
    r"position|traffic|statistic|tariff"
)


class PortAuthorities(Connector):
    ds_id = "DS-PORT-07"
    title = "Chittagong / Mongla Port Authority websites"
    # Manual drops of the CPA berthing report (A-027); more PDFs go to data/inbox/DS-PORT-07/.
    parsers = {"cpa_berthing_2026-01-05.pdf": parse_cpa_berthing}
    record_types = (PortZoneRecord, VesselRecord, PortCallRecord, PortStateSnapshotRecord)

    def probe(self, ctx: ProbeContext) -> None:
        for site, root in SITES.items():
            robots = ctx.http(ProbeCall(f"{site}_robots", f"{root}/robots.txt", "meta"))
            home = ctx.http(
                ProbeCall(f"{site}_home", f"{root}/", "meta", decode=html_outline, timeout_s=60)
            )
            links = (home.parsed or {}).get("links", []) if isinstance(home.parsed, dict) else []
            hits = sorted(
                {
                    f"{link['text'][:50]} -> {link['href'][:120]}"
                    for link in links
                    if INTERESTING.search(link["text"] + " " + link["href"])
                }
            )
            ctx.metric(f"{site}_relevant_links", hits[:40])
            ctx.metric(
                f"{site}_robots_disallow",
                [
                    line.strip()
                    for line in robots.body.decode("utf-8", "replace").splitlines()
                    if line.lower().startswith("disallow")
                ][:20]
                if robots.ok
                else f"HTTP {robots.status}",
            )


CONNECTOR = PortAuthorities()
