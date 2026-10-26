"""DS-SAT-04 · GFW SAR vessel detections (Sentinel-1), via the 4Wings report API.

Precomputed detections of industrial vessels, matched to AIS where possible; ~5-day latency.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from functools import partial

from cportal_core.areas import bbox
from cportal_core.schemas.records import SatelliteObservationRecord

from cportal_connectors.base import Connector, FieldNote
from cportal_connectors.gfw import SAR, entries, report
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.maritime import parse_gfw_sar


class GfwSar(Connector):
    ds_id = "DS-SAT-04"
    title = "GFW SAR vessel detections"
    parsers = {"sar_ctg_daily.zip": partial(parse_gfw_sar, area="ctg_outer_anchorage")}
    record_types = (SatelliteObservationRecord,)
    needs = ("GFW_API_TOKEN",)
    field_notes = {
        "sar_ctg_daily:detections": FieldNote("count", "SAR detections in the cell/period"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        if not ctx.has("GFW_API_TOKEN"):
            return
        today = datetime.now(UTC).date()
        daily = report(
            ctx,
            "sar_ctg_daily",
            {
                "spatial-resolution": "LOW",
                "temporal-resolution": "DAILY",
                "group-by": "FLAG",
                "datasets[0]": SAR,
                "format": "JSON",
                "spatial-aggregation": "true",
                "date-range": f"{today - timedelta(days=120)},{today}",
            },
            bbox("ctg_outer_anchorage"),
            note="SAR detections per day, outer anchorage, 120 days",
        )
        monthly = report(
            ctx,
            "sar_ctg_monthly_history",
            {
                "spatial-resolution": "LOW",
                "temporal-resolution": "MONTHLY",
                "group-by": "FLAG",
                "datasets[0]": SAR,
                "format": "JSON",
                "spatial-aggregation": "true",
                "date-range": f"2017-01-01,{today}",
            },
            bbox("ctg_outer_anchorage"),
            "oversized",
            note="2017 to today in one request: is there a maximum date range?",
        )
        report(
            ctx,
            "bad_resolution",
            {
                "spatial-resolution": "LOW",
                "temporal-resolution": "FORTNIGHTLY",
                "group-by": "FLAG",
                "datasets[0]": SAR,
                "format": "JSON",
                "date-range": f"{today - timedelta(days=30)},{today}",
            },
            bbox("ctg_outer_anchorage"),
            "bad_param",
            sample=False,
        )
        rows = entries(daily.parsed)
        ctx.metric("daily_rows", len(rows))
        if rows:
            ctx.metric("daily_columns", sorted(rows[0]))
            days = Counter(str(r.get("date"))[:10] for r in rows)
            ctx.metric("days_with_detections", len(days))
            ctx.metric("latest_day", max(days))
            ctx.metric(
                "detections_by_day",
                {
                    d: sum(
                        int(r.get("detections") or 0) for r in rows if str(r.get("date"))[:10] == d
                    )
                    for d in sorted(days)
                },
            )
        months = entries(monthly.parsed)
        if months:
            ctx.metric("monthly_rows", len(months))
            ctx.metric("first_month", min(str(r.get("date")) for r in months))


CONNECTOR = GfwSar()
