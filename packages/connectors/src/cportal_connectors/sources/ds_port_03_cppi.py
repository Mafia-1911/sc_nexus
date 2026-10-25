"""DS-PORT-03 · Container Port Performance Index 2020-2024 (World Bank / S&P, Sept 2025)."""

from __future__ import annotations

import re

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext

PAGE = "https://ppp.worldbank.org/node/10196"


class Cppi(Connector):
    ds_id = "DS-PORT-03"
    title = "Container Port Performance Index (CPPI)"

    def probe(self, ctx: ProbeContext) -> None:
        page = ctx.http(ProbeCall("ppp_page", PAGE, "meta", decode=html_outline))
        links = (page.parsed or {}).get("links", []) if isinstance(page.parsed, dict) else []
        files = sorted(
            {
                link["href"]
                for link in links
                if re.search(r"\.(pdf|xlsx?|csv|zip)(\?|$)", link["href"], re.I)
            }
        )
        ctx.metric("file_links", files[:20])
        for i, url in enumerate(files[:3]):
            ctx.http(
                ProbeCall(
                    f"file_{i}",
                    url if url.startswith("http") else f"https://ppp.worldbank.org{url}",
                    max_bytes=65_536,
                    note="first 64 KiB: availability and size",
                )
            )
        ctx.http(
            ProbeCall(
                "okr_search",
                "https://openknowledge.worldbank.org/server/api/discover/search/objects",
                "meta",
                params={"query": "Container Port Performance Index 2024", "size": 5},
            )
        )


CONNECTOR = Cppi()
