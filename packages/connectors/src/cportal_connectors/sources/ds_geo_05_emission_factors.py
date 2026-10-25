"""DS-GEO-05 · Emission factors: UK DESNZ GHG conversion factors (open), GLEC method (ISO 14083).

GLEC Framework v3.2 default values are restricted to Smart Freight Centre members and certified
tools, so CO2e factors come from DESNZ; GLEC/ISO 14083 provides the calculation method only.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any

import openpyxl

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext

CONTENT_API = "https://www.gov.uk/api/content/government/publications/greenhouse-gas-reporting-conversion-factors-{year}"
FREIGHT_LEVEL1 = {
    "Freighting goods",
    "Delivery vehicles",
    "Managed assets- vehicles",
    "WTT- delivery vehs & freight",
}


def flat_rows(body: bytes) -> list[dict[str, Any]]:
    """The flat file's factor table: find the header row (it starts with 'ID'), then read rows."""
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    rows: list[dict[str, Any]] = []
    for ws in wb.worksheets:
        header: list[str] | None = None
        for values in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).strip() for v in values]
            if header is None:
                if cells and cells[0] == "ID" and "Scope" in cells:
                    header = cells
                continue
            if not any(cells):
                continue
            rows.append({h: v for h, v in zip(header, values, strict=False) if h})
        if header is not None:
            break
    wb.close()
    return rows


def freight_csv(body: bytes) -> bytes:
    rows = [r for r in flat_rows(body) if str(r.get("Level 1", "")) in FREIGHT_LEVEL1]
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out.getvalue().encode()


class EmissionFactors(Connector):
    ds_id = "DS-GEO-05"
    title = "Emission factors (UK DESNZ; GLEC method)"
    field_notes = {
        "desnz_flat:Level 1": FieldNote("", "Top category, e.g. 'Freighting goods'"),
        "desnz_flat:Level 2": FieldNote("", "Mode, e.g. 'HGV (all diesel)', 'Rail', 'Cargo ship'"),
        "desnz_flat:Level 3": FieldNote("", "Vehicle class / ship type"),
        "desnz_flat:UOM": FieldNote("", "Activity unit: tonne.km, km, ..."),
        "desnz_flat:GHG/Unit": FieldNote("", "kg CO2e, kg CO2, kg CH4, kg N2O"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        content = ctx.http(
            ProbeCall(
                "content_api_2026",
                CONTENT_API.format(year=2026),
                "meta",
                note="GOV.UK content API lists the publication's files",
            )
        )
        flat_url = self._attachment(content.parsed, "flat file")
        flat = ctx.http(
            ProbeCall(
                "desnz_flat",
                flat_url or "",
                decode=flat_rows,
                records="",
                sample=True,
                sample_transform=freight_csv,
                sample_ext="csv",
                note="2026 flat file; sample keeps freight rows only",
            )
        )
        ctx.http(ProbeCall("missing_year", CONTENT_API.format(year=1999), "bad_param"))
        ctx.http(
            ProbeCall("client_timeout", CONTENT_API.format(year=2026), "timeout", timeout_s=0.001)
        )
        if isinstance(flat.parsed, list):
            rows = flat.parsed
            freight = [r for r in rows if str(r.get("Level 1", "")) in FREIGHT_LEVEL1]
            ctx.metric("rows_total", len(rows))
            ctx.metric("freight_rows", len(freight))
            ctx.metric(
                "freight_level2",
                dict(Counter(f"{r.get('Level 1')} / {r.get('Level 2')}" for r in freight)),
            )
            factor_col = next((k for k in rows[0] if "Conversion Factor" in k), None)
            ctx.metric("factor_column", factor_col)
            ctx.metric(
                "tonne_km_co2e_examples",
                [
                    {
                        k: r.get(k)
                        for k in (
                            "Level 2",
                            "Level 3",
                            "Level 4",
                            "Column Text",
                            "UOM",
                            "GHG/Unit",
                            factor_col,
                        )
                    }
                    for r in freight
                    if r.get("UOM") == "tonne.km" and r.get("GHG/Unit") == "kg CO2e"
                ][:40],
            )

    @staticmethod
    def _attachment(doc: Any, title_part: str) -> str | None:
        if not isinstance(doc, dict):
            return None
        for att in (doc.get("details") or {}).get("attachments") or []:
            if title_part in str(att.get("title", "")).lower() and str(att.get("url", "")).endswith(
                ".xlsx"
            ):
                return str(att["url"])
        return None


CONNECTOR = EmissionFactors()
