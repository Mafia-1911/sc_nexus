"""DS-WX-03 · IBTrACS v04r01 (NOAA NCEI): cyclone best tracks for scenarios and backtests."""

from __future__ import annotations

from collections import Counter
from typing import Any

from cportal_core.areas import bbox

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import csv_records
from cportal_connectors.harness import ProbeContext

BASE = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"


def _rows(body: bytes) -> list[dict[str, Any]]:
    rows = csv_records(body, limit=None)
    return rows[1:]  # the second line holds units, not data


class Ibtracs(Connector):
    ds_id = "DS-WX-03"
    title = "IBTrACS cyclone tracks"
    field_notes = {
        "last3years:ISO_TIME": FieldNote("UTC", "Fix time, 3-hourly"),
        "last3years:USA_WIND": FieldNote("kt", "Max sustained wind (JTWC)"),
        "last3years:DIST2LAND": FieldNote("km", "Distance to land"),
        "last3years:BASIN": FieldNote("", "NI = North Indian"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        recent = ctx.http(
            ProbeCall(
                "last3years",
                f"{BASE}/ibtracs.last3years.list.v04r01.csv",
                decode=_rows,
                records="",
                timeout_s=180,
                note="all basins, last three years",
            )
        )
        ctx.http(
            ProbeCall(
                "north_indian_head",
                f"{BASE}/ibtracs.NI.list.v04r01.csv",
                "meta",
                max_bytes=65_536,
                note="North Indian basin, full history",
            )
        )
        ctx.http(
            ProbeCall(
                "missing_file", f"{BASE}/ibtracs.XX.list.v04r01.csv", "bad_param", max_bytes=4096
            )
        )
        rows = recent.parsed if isinstance(recent.parsed, list) else []
        box = bbox("bay_of_bengal_approach")
        near = [
            r
            for r in rows
            if r.get("BASIN") == "NI"
            and isinstance(r.get("LAT"), float)
            and box.lat_min - 2 <= r["LAT"] <= box.lat_max + 2
            and box.lon_min - 2 <= r["LON"] <= box.lon_max + 2
        ]
        storms = Counter(f"{r.get('SEASON')} {r.get('NAME')}" for r in near)
        ctx.metric("ni_storms_near_bangladesh_last3y", dict(storms))
        ctx.metric("latest_fix", max((str(r.get("ISO_TIME")) for r in rows), default=None))


CONNECTOR = Ibtracs()
