"""DS-PORT-02 · UNCTADstat port-call statistics (median time in port; MarineTraffic-derived)."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext

PAGES = {
    "portcalls_detail_annual": "https://stats.unctad.org/portcalls_detail_a",
    "portcalls_number_annual": "https://stats.unctad.org/portcalls_number_a",
    "maritime_profile_bgd": "https://unctadstat.unctad.org/CountryProfile/MaritimeProfile/en-GB/050/index.html",
}


class Unctad(Connector):
    ds_id = "DS-PORT-02"
    title = "UNCTADstat port-call statistics"

    def probe(self, ctx: ProbeContext) -> None:
        for name, url in PAGES.items():
            result = ctx.http(
                ProbeCall(
                    name,
                    url,
                    "meta",
                    decode=html_outline,
                    note="short link; records the redirect target",
                )
            )
            ctx.metric(
                f"{name}_final",
                {
                    "http": result.status,
                    "title": (result.parsed or {}).get("title")
                    if isinstance(result.parsed, dict)
                    else None,
                },
            )
        ctx.http(
            ProbeCall(
                "legacy_bulk_7z",
                "https://unctadstat.unctad.org/7zip/US_PortCalls.csv.7z",
                "bad_param",
                max_bytes=4096,
                note="pre-2024 bulk download path; expected to be retired",
            )
        )


CONNECTOR = Unctad()
