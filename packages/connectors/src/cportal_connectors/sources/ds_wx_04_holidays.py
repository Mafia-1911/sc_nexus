"""DS-WX-04 · `holidays` package, Bangladesh calendar (Eid dates move with the Hijri calendar)."""

from __future__ import annotations

import importlib.metadata as md
import json

import holidays

from cportal_connectors.base import Connector, FieldNote
from cportal_connectors.harness import ProbeContext

YEARS = range(2019, 2028)


class BdHolidays(Connector):
    ds_id = "DS-WX-04"
    title = "holidays package: Bangladesh"
    field_notes = {
        "bd_holidays:date": FieldNote("ISO date (local)", "Holiday date in Asia/Dhaka"),
        "bd_holidays:name": FieldNote("", "Holiday name; '(estimated)' marks computed Hijri dates"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        dist = md.distribution("holidays")
        ctx.metric(
            "package",
            {
                "version": dist.version,
                "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
            },
        )
        bd = holidays.country_holidays("BD", years=YEARS)
        rows = [{"date": d.isoformat(), "name": name} for d, name in sorted(bd.items())]
        ctx.record_local(
            "bd_holidays",
            request={"url": "holidays.country_holidays('BD')", "years": list(YEARS)},
            body=json.dumps(rows, ensure_ascii=False).encode(),
            ext="json",
            records="",
            sample=True,
        )
        supported = holidays.list_supported_countries().get("BD", [])
        ctx.metric("supported_subdivisions", supported)
        categories = getattr(holidays.country_holidays("BD"), "supported_categories", None)
        ctx.metric("supported_categories", sorted(categories) if categories else None)
        per_year: dict[int, int] = {}
        eid: dict[str, list[str]] = {}
        for row in rows:
            year = int(row["date"][:4])
            per_year[year] = per_year.get(year, 0) + 1
            if "Eid" in row["name"] or "Fitr" in row["name"] or "Adha" in row["name"]:
                eid.setdefault(row["date"][:4], []).append(f"{row['date']} {row['name']}")
        ctx.metric("holidays_per_year", per_year)
        ctx.metric("eid_dates", eid)
        ctx.metric(
            "estimated_share",
            round(sum("estimated" in r["name"].lower() for r in rows) / len(rows), 3)
            if rows
            else None,
        )


CONNECTOR = BdHolidays()
