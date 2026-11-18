"""DS-TRADE-05 · USITC Harmonized Tariff Schedule REST API (`hts.usitc.gov/reststop`).

No key; US government work (public domain). One `exportList` call per watched heading gives the
general, special and column-2 rates; one call over Chapter 99 (9903.01-9903.07) gives the
country surcharges and exemptions. `to` is exclusive (probed 2026-11-18).
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
from cportal_connectors.parsers.tariffs import hts_parser
from cportal_connectors.tariff_watch import next_heading, watched_headings, watchlist

EXPORT = "https://hts.usitc.gov/reststop/exportList"


def _params(start: str, end: str) -> dict[str, str]:
    return {"from": start, "to": end, "format": "JSON", "styles": "false"}


class UsitcHts(Connector):
    ds_id = "DS-TRADE-05"
    title = "USITC Harmonized Tariff Schedule REST API"
    live_every_min = 1440
    parsers = {
        "hts_export_6109.json": hts_parser("hts:6109"),
        "hts_export_9903_01_07.json": hts_parser("hts:9903.01-9903.07"),
    }
    record_types = (
        TariffNomenclatureRecord,
        TariffOriginGroupRecord,
        TariffOriginMemberRecord,
        TariffMeasureRecord,
        TariffSnapshotRecord,
    )
    field_notes = {
        "hts_export_6109:general": FieldNote("%", "Column 1 general (MFN) rate, verbatim"),
        "hts_export_6109:special": FieldNote("", "Preferential rates with programme codes"),
        "hts_export_6109:other": FieldNote("%", "Column 2 rate (no normal trade relations)"),
        "hts_export_9903_01_07:general": FieldNote("", "Surcharge: 'applicable subheading + N%'"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "hts_export_6109",
                EXPORT,
                params=_params("6109", "6110"),
                sample=True,
                ext="json",  # the server says application/octet-stream
                note="heading 6109 (to is exclusive)",
            )
        )
        start, end = watchlist()["us_chapter99"]
        ctx.http(
            ProbeCall(
                "hts_export_9903_01_07",
                EXPORT,
                params=_params(start, end),
                sample=True,
                ext="json",
                note="Chapter 99 country surcharges",
            )
        )
        ctx.http(ProbeCall("bad_range", EXPORT, "bad_param", params=_params("ZZZZ", "0000")))

    def live(self, http: LiveHttp) -> list[Record]:
        out: list[Record] = []
        calls = [(f"hts_export_{h}", h, next_heading(h), f"hts:{h}") for h in watched_headings()]
        start, end = watchlist()["us_chapter99"]
        calls.append(
            (f"hts_export_{start}_{end}".replace(".", "_"), start, end, f"hts:{start}-{end}")
        )
        for name, a, b, scope in calls:
            body = http.get(name, EXPORT, _params(a, b))
            try:
                out += hts_parser(scope)(body, http.ctx())
            except (ValueError, KeyError, TypeError) as exc:
                raise LiveError(f"{name}: unparseable response ({type(exc).__name__})") from exc
        return out


CONNECTOR = UsitcHts()
