"""DS-TRADE-03 · World Bank Indicators API v2 (WDI, LPI): annual country indicators."""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext

BASE = "https://api.worldbank.org/v2"
INDICATORS = {
    "LP.LPI.OVRL.XQ": "Logistics Performance Index, overall (1=low to 5=high)",
    "LP.LPI.TIME.XQ": "LPI: timeliness of shipments (1-5)",
    "IS.SHP.GOOD.TU": "Container port traffic (TEU: 20 foot equivalent units)",
    "IS.SHP.GCNW.XQ": "Liner shipping connectivity index (maximum value in 2023 = 100)",
    "TX.VAL.MRCH.CD.WT": "Merchandise exports (current US$)",
}


class WorldBank(Connector):
    ds_id = "DS-TRADE-03"
    title = "World Bank Indicators API v2"
    field_notes = {
        "indicators_bgd:value": FieldNote("per indicator", "Annual value; null when not reported"),
        "indicators_bgd:date": FieldNote("year", "Reporting year as a string"),
        "indicators_bgd:indicator.id": FieldNote("", "WDI indicator code"),
        "indicators_bgd:countryiso3code": FieldNote("", "ISO 3166-1 alpha-3"),
        "indicators_bgd:obs_status": FieldNote("", "Observation status flag (often empty)"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        codes = ";".join(INDICATORS)
        main = ctx.http(
            ProbeCall(
                "indicators_bgd",
                f"{BASE}/country/BGD/indicator/{codes}",
                sample=True,
                records="1[]",
                params={"format": "json", "source": 2, "date": "2007:2026", "per_page": 1000},
                note="five WDI indicators for Bangladesh, 2007-2026 (multi-indicator: source=2)",
            )
        )
        ctx.http(
            ProbeCall(
                "indicator_meta",
                f"{BASE}/indicator/LP.LPI.OVRL.XQ",
                "meta",
                params={"format": "json"},
            )
        )
        ctx.http(
            ProbeCall(
                "bad_indicator",
                f"{BASE}/country/BGD/indicator/NOT.A.CODE",
                "bad_param",
                params={"format": "json"},
            )
        )
        ctx.http(
            ProbeCall(
                "bad_country",
                f"{BASE}/country/XXX/indicator/LP.LPI.OVRL.XQ",
                "bad_param",
                params={"format": "json"},
            )
        )
        ctx.http(
            ProbeCall(
                "no_data_years",
                f"{BASE}/country/BGD/indicator/LP.LPI.OVRL.XQ",
                "empty",
                params={"format": "json", "date": "1960:1965"},
            )
        )
        ctx.http(
            ProbeCall(
                "page_past_end",
                f"{BASE}/country/BGD/indicator/LP.LPI.OVRL.XQ",
                "last_page",
                params={"format": "json", "page": 99},
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{BASE}/country/BGD/indicator/LP.LPI.OVRL.XQ",
                "timeout",
                params={"format": "json"},
                timeout_s=0.001,
            )
        )
        if isinstance(main.parsed, list) and len(main.parsed) == 2:
            self._metrics(ctx, main.parsed)

    def _metrics(self, ctx: ProbeContext, doc: list[Any]) -> None:
        ctx.metric("page_meta", doc[0])
        coverage: dict[str, dict[str, Any]] = {}
        for rec in doc[1] or []:
            code = rec["indicator"]["id"]
            entry = coverage.setdefault(code, {"years_with_value": [], "latest": None})
            if rec["value"] is not None:
                entry["years_with_value"].append(rec["date"])
                if entry["latest"] is None or rec["date"] > entry["latest"][0]:
                    entry["latest"] = (rec["date"], rec["value"])
        for entry in coverage.values():
            entry["years_with_value"] = sorted(entry["years_with_value"])
        ctx.metric("bgd_coverage", coverage)


CONNECTOR = WorldBank()
