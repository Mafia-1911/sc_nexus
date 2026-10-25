"""DS-AIS-02 · Global Fishing Watch API v3: port visits, vessel identity, AIS presence.

The only free, vessel-level history of Chattogram port calls (labels for C4). CC BY-NC 4.0.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_core.areas import BBox, bbox

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.gfw import (
    API,
    IDENTITY,
    PORT_VISITS,
    PRESENCE,
    auth,
    entries,
    polygon,
    report,
)
from cportal_connectors.harness import ProbeContext


def ctg_envelope() -> BBox:
    a, r = bbox("ctg_outer_anchorage"), bbox("ctg_port_river")
    return BBox(
        min(a.lon_min, r.lon_min),
        min(a.lat_min, r.lat_min),
        max(a.lon_max, r.lon_max),
        max(a.lat_max, r.lat_max),
    )


class GlobalFishingWatch(Connector):
    ds_id = "DS-AIS-02"
    title = "Global Fishing Watch API v3"
    needs = ("GFW_API_TOKEN",)
    field_notes = {
        "port_visits_ctg_90d:start": FieldNote("UTC ISO 8601", "Visit start"),
        "port_visits_ctg_90d:end": FieldNote("UTC ISO 8601", "Visit end"),
        "port_visits_ctg_90d:port_visit.durationHrs": FieldNote("hours", "Visit duration"),
        "port_visits_ctg_90d:port_visit.confidence": FieldNote(
            "2-4", "4 = entry, stop and exit all observed"
        ),
        "port_visits_ctg_90d:vessel.ssvid": FieldNote("", "MMSI as reported (string)"),
        "port_visits_ctg_90d:vessel.id": FieldNote("", "GFW vessel ID (join to identity)"),
        "port_visits_ctg_90d:vessel.type": FieldNote("", "GFW vessel class (cargo, other, ...)"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "no_token",
                f"{API}/events",
                "no_key",
                params={"datasets[0]": PORT_VISITS, "limit": 1, "offset": 0},
            )
        )
        ctx.http(
            ProbeCall(
                "bad_token",
                f"{API}/events",
                "bad_key",
                headers={"Authorization": "Bearer not-a-real-token"},
                params={"datasets[0]": PORT_VISITS, "limit": 1, "offset": 0},
            )
        )
        if not ctx.has("GFW_API_TOKEN"):
            return
        today = datetime.now(UTC).date()
        start, end = today - timedelta(days=90), today
        body = {
            "datasets": [PORT_VISITS],
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "geometry": polygon(ctg_envelope()),
        }
        visits = ctx.http(
            ProbeCall(
                "port_visits_ctg_90d",
                f"{API}/events",
                method="POST",
                params={"offset": 0, "limit": 1000},
                headers=auth(ctx),
                json_body=body,
                records="entries[]",
                sample=True,
                timeout_s=120,
                note=f"port visits in the Chattogram envelope, {start}..{end}",
            )
        )
        all_visits = list((visits.parsed or {}).get("entries", []))
        offset = (visits.parsed or {}).get("nextOffset")
        while isinstance(offset, int) and offset > 0 and len(all_visits) < 5000:
            page = ctx.http(
                ProbeCall(
                    f"port_visits_ctg_90d_offset_{offset}",
                    f"{API}/events",
                    method="POST",
                    params={"offset": offset, "limit": 1000},
                    headers=auth(ctx),
                    json_body=body,
                    timeout_s=120,
                    group="port_visits_pages",
                    note="pagination via nextOffset",
                )
            )
            page_doc = page.parsed if isinstance(page.parsed, dict) else {}
            all_visits += page_doc.get("entries", [])
            offset = page_doc.get("nextOffset")
            page.body, page.parsed = b"", None
        for year in (2019, 2022, 2025):
            ctx.http(
                ProbeCall(
                    f"port_visits_ctg_{year}_count",
                    f"{API}/events",
                    "meta",
                    method="POST",
                    params={"offset": 0, "limit": 1},
                    headers=auth(ctx),
                    timeout_s=120,
                    json_body={
                        **body,
                        "startDate": f"{year}-01-01",
                        "endDate": f"{year + 1}-01-01",
                    },
                    note="limit=1 to read `total`: visits per year (history depth)",
                )
            )
        ctx.http(
            ProbeCall(
                "port_visits_mongla_90d",
                f"{API}/events",
                method="POST",
                params={"offset": 0, "limit": 200},
                headers=auth(ctx),
                records="entries[]",
                json_body={**body, "geometry": polygon(bbox("mongla"))},
                sample=True,
            )
        )
        vessel_id = self._first_vessel(visits.parsed)
        if vessel_id:
            ctx.http(
                ProbeCall(
                    "vessel_identity",
                    f"{API}/vessels/{vessel_id}",
                    sample=True,
                    headers=auth(ctx),
                    params={"dataset": IDENTITY},
                )
            )
        ctx.http(
            ProbeCall(
                "vessel_search",
                f"{API}/vessels/search",
                sample=True,
                headers=auth(ctx),
                records="entries[]",
                params={"query": "CHATTOGRAM", "datasets[0]": IDENTITY, "limit": 5},
                note="free-text search; the name is just a probe term",
            )
        )
        presence_start = today - timedelta(days=40)
        presence = report(
            ctx,
            "presence_ctg_anchorage_daily",
            {
                "spatial-resolution": "LOW",
                "temporal-resolution": "DAILY",
                "group-by": "VESSEL_ID",
                "datasets[0]": PRESENCE,
                "format": "JSON",
                "spatial-aggregation": "true",
                "date-range": f"{presence_start},{today}",
            },
            bbox("ctg_outer_anchorage"),
            note="AIS presence hours per vessel per day in the outer anchorage (40 days)",
        )
        ctx.http(
            ProbeCall(
                "bad_dataset",
                f"{API}/events",
                "bad_param",
                headers=auth(ctx),
                params={"datasets[0]": "no-such-dataset:latest", "limit": 1, "offset": 0},
            )
        )
        ctx.http(
            ProbeCall(
                "page_past_end",
                f"{API}/events",
                "last_page",
                method="POST",
                params={"offset": 100000, "limit": 10},
                headers=auth(ctx),
                json_body=body,
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{API}/events",
                "timeout",
                headers=auth(ctx),
                params={"datasets[0]": PORT_VISITS, "limit": 1, "offset": 0},
                timeout_s=0.001,
            )
        )
        ctx.metric("visits_90d_total", (visits.parsed or {}).get("total"))
        self._visit_metrics(ctx, all_visits)
        self._presence_metrics(ctx, entries(presence.parsed))

    @staticmethod
    def _first_vessel(doc: Any) -> str | None:
        for entry in (doc or {}).get("entries", []) if isinstance(doc, dict) else []:
            vessel = entry.get("vessel") or {}
            if vessel.get("id"):
                return str(vessel["id"])
        return None

    @staticmethod
    def _quantiles(values: list[float]) -> dict[str, float] | None:
        if len(values) < 10:
            return None
        q = statistics.quantiles(values, n=10)
        return {
            "n": len(values),
            "p10": round(q[0], 1),
            "p50": round(statistics.median(values), 1),
            "p90": round(q[-1], 1),
        }

    def _visit_metrics(self, ctx: ProbeContext, rows: list[dict[str, Any]]) -> None:
        ctx.metric("visits_90d_fetched", len(rows))
        ctx.metric(
            "visits_by_vessel_type",
            dict(Counter(str((r.get("vessel") or {}).get("type")) for r in rows)),
        )
        ctx.metric(
            "visits_by_confidence",
            dict(Counter(str((r.get("port_visit") or {}).get("confidence")) for r in rows)),
        )
        ctx.metric(
            "visit_start_years",
            dict(sorted(Counter(str(r.get("start"))[:4] for r in rows).items())),
        )
        hours = [float((r.get("port_visit") or {}).get("durationHrs") or 0) for r in rows]
        ctx.metric("duration_hours_all", self._quantiles([h for h in hours if h > 0]))
        # Calibration subset: cargo, confidence 4, started inside the window, under 60 days.
        cargo = [
            r
            for r in rows
            if (r.get("vessel") or {}).get("type") == "cargo"
            and str((r.get("port_visit") or {}).get("confidence")) == "4"
            and 0 < float((r.get("port_visit") or {}).get("durationHrs") or 0) < 24 * 60
        ]
        ctx.metric(
            "duration_hours_cargo_conf4_lt60d",
            self._quantiles([float(r["port_visit"]["durationHrs"]) for r in cargo]),
        )
        dock: Counter[str] = Counter()
        for r in cargo:
            pv = r["port_visit"]
            pattern = "/".join(
                "dock" if (pv.get(k) or {}).get("atDock") else "anchor"
                for k in ("startAnchorage", "intermediateAnchorage", "endAnchorage")
            )
            dock[pattern] += 1
        ctx.metric("cargo_stop_patterns_start_mid_end", dict(dock.most_common()))
        anchorages: Counter[str] = Counter()
        for r in rows:
            pv = r.get("port_visit") or {}
            for key in ("startAnchorage", "intermediateAnchorage", "endAnchorage"):
                a = pv.get(key) or {}
                if a.get("anchorageId"):
                    where = "dock" if a.get("atDock") else "anchor"
                    anchorages[
                        f"{a.get('anchorageId')} {where} ({a.get('lat'):.3f},{a.get('lon'):.3f})"
                    ] += 1
        ctx.metric("top_anchorage_cells", dict(anchorages.most_common(15)))
        ctx.metric(
            "port_ids",
            dict(
                Counter(
                    str(((r.get("port_visit") or {}).get("intermediateAnchorage") or {}).get("id"))
                    for r in rows
                )
            ),
        )

    @staticmethod
    def _presence_metrics(ctx: ProbeContext, rows: list[dict[str, Any]]) -> None:
        if not rows:
            ctx.metric("presence_rows", 0)
            return
        ctx.metric("presence_rows", len(rows))
        ctx.metric("presence_columns", sorted(rows[0]))
        ctx.metric("presence_by_vessel_type", dict(Counter(str(r.get("vesselType")) for r in rows)))
        per_day: dict[str, set[str]] = {}
        cargo_day: dict[str, set[str]] = {}
        for r in rows:
            day = str(r.get("date"))[:10]
            per_day.setdefault(day, set()).add(str(r.get("vesselId")))
            if r.get("vesselType") == "CARGO":
                cargo_day.setdefault(day, set()).add(str(r.get("vesselId")))
        ctx.metric("vessels_present_per_day", {d: len(v) for d, v in sorted(per_day.items())})
        ctx.metric("cargo_present_per_day", {d: len(v) for d, v in sorted(cargo_day.items())})
        ctx.metric("latest_presence_day", max(per_day))
        ctx.metric("latest_transmission", max(str(r.get("lastTransmissionDate")) for r in rows))


CONNECTOR = GlobalFishingWatch()
