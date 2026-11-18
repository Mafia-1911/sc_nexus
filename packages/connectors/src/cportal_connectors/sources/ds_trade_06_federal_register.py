"""DS-TRADE-06 · Federal Register API v1: official US notices about the tariff schedule.

No key; public domain. The newest documents that mention the HTS, kept only when a trade
agency (USTR, ITA, ITC, CBP, the President's office, BIS) issued them.
"""

from __future__ import annotations

from urllib.parse import urlencode

from cportal_core.schemas.records import TradePolicyNoticeRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.live import LiveCall, LiveHttp
from cportal_connectors.parsers.tariffs import parse_federal_register

BASE = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = (
    "document_number",
    "title",
    "type",
    "publication_date",
    "effective_on",
    "html_url",
    "abstract",
    "agencies",
    "excerpts",
)


def documents_url(per_page: int = 50) -> str:
    query = [
        ("conditions[term]", '"Harmonized Tariff Schedule"'),
        ("order", "newest"),
        ("per_page", str(per_page)),
        *[("fields[]", f) for f in FIELDS],
    ]
    return f"{BASE}?{urlencode(query)}"


class FederalRegister(Connector):
    ds_id = "DS-TRADE-06"
    title = "Federal Register API (US trade notices)"
    live_every_min = 360
    parsers = {"fr_hts_documents.json": parse_federal_register}
    record_types = (TradePolicyNoticeRecord,)
    field_notes = {
        "fr_hts_documents:results[].publication_date": FieldNote("date", "Publication date"),
        "fr_hts_documents:results[].effective_on": FieldNote("date", "Effective date (often null)"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "fr_hts_documents",
                documents_url(20),
                sample=True,
                records="results[]",
                note="newest documents mentioning the HTS",
            )
        )

    def live_calls(self, http: LiveHttp) -> list[LiveCall]:
        return [LiveCall("fr_hts_documents", documents_url(), parse_federal_register)]


CONNECTOR = FederalRegister()
