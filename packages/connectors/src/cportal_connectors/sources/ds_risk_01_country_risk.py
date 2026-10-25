"""DS-RISK-01 · Country risk: WGI (World Bank API, source 3), INFORM Risk, ND-GAIN."""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.landing import landing_and_files

WB = "https://api.worldbank.org/v2"
COUNTRIES = "BGD;CHN;IND;VNM;LKA;MMR"  # Bangladesh and its main input suppliers and peers
WGI = "GE.EST;PV.EST;RQ.EST;CC.EST"


class CountryRisk(Connector):
    ds_id = "DS-RISK-01"
    title = "WGI, INFORM Risk, ND-GAIN"
    field_notes = {
        "wgi:value": FieldNote("z-score ≈ -2.5..2.5", "WGI estimate; higher is better"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        wgi = ctx.http(
            ProbeCall(
                "wgi",
                f"{WB}/country/{COUNTRIES}/indicator/{WGI}",
                sample=True,
                records="1[]",
                params={"source": 3, "format": "json", "date": "2018:2025", "per_page": 1000},
            )
        )
        landing_and_files(
            ctx,
            "inform",
            "https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Results-and-data",
            r"\.(xlsx?|zip)(\?|$)",
        )
        landing_and_files(
            ctx,
            "ndgain",
            "https://gain.nd.edu/our-work/country-index/download-data/",
            r"\.(zip|csv)(\?|$)",
            max_files=1,
        )
        self._wgi(ctx, wgi.parsed)

    @staticmethod
    def _wgi(ctx: ProbeContext, doc: Any) -> None:
        if not (isinstance(doc, list) and len(doc) == 2 and isinstance(doc[1], list)):
            return
        latest: dict[str, dict[str, Any]] = {}
        for rec in doc[1]:
            if rec.get("value") is None:
                continue
            key = f"{rec['countryiso3code']} {rec['indicator']['id']}"
            if key not in latest or rec["date"] > latest[key]["year"]:
                latest[key] = {"year": rec["date"], "value": round(rec["value"], 2)}
        ctx.metric("wgi_latest", dict(sorted(latest.items())))


CONNECTOR = CountryRisk()
