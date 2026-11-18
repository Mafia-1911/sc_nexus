"""DS-TRADE-07 · UK Trade Tariff API v2 (`trade-tariff.service.gov.uk/api/v2`).

No key; Open Government Licence (to verify). Per watched heading, the heading tree gives the
declarable 10-digit commodities; each watched commodity's document gives its import measures
with origin groups and their member countries (DCTS, FTAs).
"""

from __future__ import annotations

from cportal_core.schemas.records import (
    Record,
    TariffMeasureRecord,
    TariffNomenclatureRecord,
    TariffOriginGroupRecord,
    TariffOriginMemberRecord,
    TariffSnapshotRecord,
)

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.live import LiveError, LiveHttp
from cportal_connectors.parsers.tariffs import (
    parse_uk_commodity,
    parse_uk_heading,
    uk_declarable_leaves,
)
from cportal_connectors.tariff_watch import watched_headings, watched_hs6

BASE = "https://www.trade-tariff.service.gov.uk/api/v2"


class UkTradeTariff(Connector):
    ds_id = "DS-TRADE-07"
    title = "UK Trade Tariff API v2"
    live_every_min = 1440
    parsers = {
        "uk_heading_6109.json": parse_uk_heading,
        "uk_commodity_6109100010.json": parse_uk_commodity,
    }
    record_types = (
        TariffNomenclatureRecord,
        TariffOriginGroupRecord,
        TariffOriginMemberRecord,
        TariffMeasureRecord,
        TariffSnapshotRecord,
    )
    field_notes = {
        "uk_commodity_6109100010:included[].attributes.base": FieldNote("", "Duty expression"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("uk_heading_6109", f"{BASE}/headings/6109", sample=True))
        ctx.http(
            ProbeCall("uk_commodity_6109100010", f"{BASE}/commodities/6109100010", sample=True)
        )
        ctx.http(ProbeCall("bad_commodity", f"{BASE}/commodities/0000000000", "bad_param"))

    def live(self, http: LiveHttp) -> list[Record]:
        out: list[Record] = []
        hs6 = set(watched_hs6())
        for heading in watched_headings():
            body = http.get(f"uk_heading_{heading}", f"{BASE}/headings/{heading}")
            try:
                out += parse_uk_heading(body, http.ctx())
                leaves = [c for c in uk_declarable_leaves(body) if c[:6] in hs6]
            except (ValueError, KeyError, TypeError) as exc:
                raise LiveError(
                    f"uk_heading_{heading}: unparseable ({type(exc).__name__})"
                ) from exc
            for code in leaves:
                doc = http.get(f"uk_commodity_{code}", f"{BASE}/commodities/{code}")
                try:
                    out += parse_uk_commodity(doc, http.ctx())
                except (ValueError, KeyError, TypeError) as exc:
                    raise LiveError(
                        f"uk_commodity_{code}: unparseable ({type(exc).__name__})"
                    ) from exc
        return out


CONNECTOR = UkTradeTariff()
