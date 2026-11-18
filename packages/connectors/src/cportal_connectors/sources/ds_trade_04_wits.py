"""DS-TRADE-04 · World Bank WITS (UNCTAD TRAINS) SDMX API: reported MFN tariffs by HS6.

No key. One call per market covers every watched HS6 code (`;`-separated). WITS publishes 1-3
years late, so the live refresh tries the newest year first and steps back on 404 (probed
2026-11-18: 2024 → 404, 2023 → 200).
"""

from __future__ import annotations

from datetime import UTC, datetime

from cportal_core.schemas.records import Record, TariffMeasureRecord, TariffSnapshotRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.live import LiveError, LiveHttp
from cportal_connectors.parsers.tariffs import parse_wits_mfn
from cportal_connectors.tariff_watch import watched_hs6, watchlist

BASE = "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN"


def url(reporter: str, year: int) -> str:
    products = ";".join(watched_hs6())
    return (
        f"{BASE}/reporter/{reporter}/partner/000/product/{products}/year/{year}/datatype/reported"
    )


class Wits(Connector):
    ds_id = "DS-TRADE-04"
    title = "World Bank WITS TRAINS (reported MFN tariffs)"
    live_every_min = 7 * 1440  # annual data: weekly is plenty
    parsers = {
        "mfn_eun_2023.xml": parse_wits_mfn,
        "mfn_usa_2023.xml": parse_wits_mfn,
        "mfn_jpn_2023.xml": parse_wits_mfn,
        "mfn_can_2023.xml": parse_wits_mfn,
    }
    record_types = (TariffMeasureRecord, TariffSnapshotRecord)
    field_notes = {
        "mfn_eun_2023:Obs@OBS_VALUE": FieldNote("%", "Simple average of the national lines"),
        "mfn_eun_2023:Obs@TOTALNOOFLINES": FieldNote("lines", "National tariff lines averaged"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        for name, rep in (("eun", "918"), ("usa", "840"), ("jpn", "392"), ("can", "124")):
            ctx.http(
                ProbeCall(
                    f"mfn_{name}_2023",
                    url(rep, 2023),
                    sample=True,
                    ext="xml",
                    note=f"reported MFN, reporter {rep}, watched HS6, 2023",
                )
            )
        ctx.http(ProbeCall("not_yet_published", url("840", 2024), "empty", ext="xml"))

    def live(self, http: LiveHttp) -> list[Record]:
        out: list[Record] = []
        this_year = datetime.now(UTC).year
        for market, m in sorted(watchlist()["markets"].items()):
            rep = m.get("wits_reporter")
            if not rep:
                continue
            for back in watchlist()["wits_years_back"]:
                year = this_year - int(back)
                try:
                    body = http.get(f"mfn_{market.lower()}_{year}", url(rep, year), ext="xml")
                except LiveError as exc:
                    if "HTTP 404" in str(exc):
                        continue  # not published yet: step back a year
                    raise
                out += parse_wits_mfn(body, http.ctx())
                break
        return out


CONNECTOR = Wits()
