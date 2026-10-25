"""DS-NEWS-06 · NY Fed Global Supply Chain Pressure Index (monthly)."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import xlsx_outline
from cportal_connectors.harness import ProbeContext

XLSX = (
    "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx"
)


class Gscpi(Connector):
    ds_id = "DS-NEWS-06"
    title = "NY Fed GSCPI"

    def probe(self, ctx: ProbeContext) -> None:
        result = ctx.http(
            ProbeCall(
                "gscpi_xlsx", XLSX, decode=lambda b: xlsx_outline(b, 12), sample=True, ext="xlsx"
            )
        )
        ctx.http(ProbeCall("page", "https://www.newyorkfed.org/research/policy/gscpi", "meta"))
        if isinstance(result.parsed, dict):
            ctx.metric(
                "sheets", {name: s["dimensions"] for name, s in result.parsed["sheets"].items()}
            )


CONNECTOR = Gscpi()
