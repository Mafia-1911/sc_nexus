"""DS-PORT-01 · IMF PortWatch: daily port calls and trade estimates via ArcGIS FeatureServer."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cportal_core.schemas.records import (
    DisruptionEventRecord,
    ExternalIdRecord,
    PortActivityDailyRecord,
)

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.ports import (
    parse_portwatch_daily,
    parse_portwatch_disruptions,
    parse_portwatch_ports,
)

HUB_SEARCH = "https://portwatch.imf.org/api/search/v1/collections/dataset/items"
SERVICES = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS = f"{SERVICES}/PortWatch_ports_database/FeatureServer/0"
DAILY = f"{SERVICES}/Daily_Ports_Data/FeatureServer/0"
DISRUPTIONS = f"{SERVICES}/portwatch_disruptions_database/FeatureServer/0"
DISRUPTION_PORTS = f"{SERVICES}/disruptions_with_ports/FeatureServer/0"


def _stat(kind: str, field: str, alias: str) -> dict[str, str]:
    return {"statisticType": kind, "onStatisticField": field, "outStatisticFieldName": alias}


class PortWatch(Connector):
    ds_id = "DS-PORT-01"
    title = "IMF PortWatch"
    parsers = {
        "daily_bgd_recent.json": parse_portwatch_daily,
        "ports_bgd.json": parse_portwatch_ports,
        "disruptions_bgd.json": parse_portwatch_disruptions,
    }
    record_types = (PortActivityDailyRecord, ExternalIdRecord, DisruptionEventRecord)
    field_notes = {
        "daily_bgd_recent:date": FieldNote("date (UTC day)", "Day of the port-call estimate"),
        "daily_bgd_recent:portcalls": FieldNote("calls/day", "All port calls, all vessel types"),
        "daily_bgd_recent:portcalls_container": FieldNote("calls/day", "Container-ship calls"),
        "daily_bgd_recent:import": FieldNote("metric tonnes", "Estimated import volume"),
        "daily_bgd_recent:export": FieldNote("metric tonnes", "Estimated export volume"),
        "daily_bgd_recent:import_container": FieldNote("metric tonnes", "Container import volume"),
        "daily_bgd_recent:portid": FieldNote("", "PortWatch port ID (join key to ports database)"),
        "ports_bgd:LOCODE": FieldNote("", "UN/LOCODE (5 chars, no space)"),
        "ports_bgd:vessel_count_total": FieldNote(
            "vessels", "Distinct vessels seen in the reference year (per PortWatch methodology)"
        ),
        "ports_bgd:share_country_maritime_import": FieldNote(
            "share 0–1", "Port's share of the country's maritime imports"
        ),
    }

    def probe(self, ctx: ProbeContext) -> None:
        since = (datetime.now(UTC).date() - timedelta(days=120)).isoformat()
        ctx.http(
            ProbeCall(
                "hub_catalogue",
                HUB_SEARCH,
                "meta",
                params={"limit": 40},
                note="ArcGIS Hub catalogue of PortWatch datasets",
            )
        )
        ctx.http(ProbeCall("ports_layer", PORTS, "meta", params={"f": "json"}))
        ctx.http(ProbeCall("daily_layer", DAILY, "meta", params={"f": "json"}))
        ports = ctx.http(
            ProbeCall(
                "ports_bgd",
                f"{PORTS}/query",
                sample=True,
                records="features[].attributes",
                params={"where": "ISO3='BGD'", "outFields": "*", "outSR": 4326, "f": "json"},
            )
        )
        daily = ctx.http(
            ProbeCall(
                "daily_bgd_recent",
                f"{DAILY}/query",
                sample=True,
                records="features[].attributes",
                params={
                    "where": f"ISO3='BGD' AND date >= DATE '{since}'",
                    "outFields": "*",
                    "orderByFields": "date DESC",
                    "resultRecordCount": 1000,
                    "f": "json",
                },
                note=f"Bangladesh ports since {since}",
            )
        )
        stats = ctx.http(
            ProbeCall(
                "daily_bgd_coverage",
                f"{DAILY}/query",
                records="features[].attributes",
                params={
                    "where": "ISO3='BGD'",
                    "groupByFieldsForStatistics": "portid,portname",
                    "outStatistics": json.dumps(
                        [
                            _stat("min", "date", "first_date"),
                            _stat("max", "date", "last_date"),
                            _stat("count", "ObjectId", "days"),
                            _stat("avg", "portcalls", "mean_calls"),
                            _stat("max", "portcalls", "max_calls"),
                        ]
                    ),
                    "f": "json",
                },
                note="history depth and freshness per Bangladesh port",
            )
        )
        disruptions = ctx.http(
            ProbeCall(
                "disruptions_bgd",
                f"{DISRUPTIONS}/query",
                sample=True,
                records="features[].attributes",
                params={
                    "where": "country LIKE '%Bangladesh%'",
                    "outFields": "*",
                    "returnGeometry": "false",
                    "orderByFields": "fromdate DESC",
                    "f": "json",
                },
            )
        )
        ctx.http(
            ProbeCall(
                "disruption_ports_bgd",
                f"{DISRUPTION_PORTS}/query",
                sample=True,
                records="features[].attributes",
                params={
                    "where": "country='Bangladesh'",
                    "outFields": "*",
                    "returnGeometry": "false",
                    "orderByFields": "fromdate DESC",
                    "f": "json",
                },
            )
        )
        # Failure modes: ArcGIS reports most errors as HTTP 200 with an "error" object.
        ctx.http(
            ProbeCall(
                "bad_field",
                f"{DAILY}/query",
                "bad_param",
                params={"where": "no_such_field=1", "outFields": "*", "f": "json"},
            )
        )
        ctx.http(
            ProbeCall(
                "no_match",
                f"{DAILY}/query",
                "empty",
                params={"where": "portid='port_does_not_exist'", "outFields": "*", "f": "json"},
            )
        )
        ctx.http(
            ProbeCall(
                "offset_past_end",
                f"{PORTS}/query",
                "last_page",
                params={
                    "where": "ISO3='BGD'",
                    "outFields": "portid",
                    "resultOffset": 100000,
                    "f": "json",
                },
            )
        )
        ctx.http(
            ProbeCall(
                "over_max_record_count",
                f"{DAILY}/query",
                "oversized",
                params={
                    "where": "ISO3='BGD'",
                    "outFields": "portid,date",
                    "resultRecordCount": 5000,
                    "f": "json",
                },
                note="asks for 5000 rows; layer maxRecordCount is 1000",
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{PORTS}/query",
                "timeout",
                timeout_s=0.001,
                params={"where": "ISO3='BGD'", "outFields": "*", "f": "json"},
            )
        )
        self._metrics(ctx, ports.parsed, daily.parsed, stats.parsed, disruptions.parsed)

    def _metrics(self, ctx: ProbeContext, ports: Any, daily: Any, stats: Any, dis: Any) -> None:
        def rows(doc: Any) -> list[dict[str, Any]]:
            return [f["attributes"] for f in (doc or {}).get("features", [])]

        ctx.metric(
            "bgd_ports",
            [
                {
                    k: p.get(k)
                    for k in (
                        "portid",
                        "portname",
                        "LOCODE",
                        "lat",
                        "lon",
                        "vessel_count_total",
                        "vessel_count_container",
                    )
                }
                for p in rows(ports)
            ],
        )
        coverage = rows(stats)
        for row in coverage:
            for key in ("first_date", "last_date"):
                if isinstance(row.get(key), int):  # epoch ms for Date fields
                    row[key] = datetime.fromtimestamp(row[key] / 1000, UTC).date().isoformat()
        ctx.metric("bgd_daily_coverage", coverage)
        last = max((str(r.get("last_date")) for r in coverage if r.get("last_date")), default=None)
        if last:
            lag = (date.today() - date.fromisoformat(last[:10])).days
            ctx.metric("freshness_lag_days", lag)
        recent = rows(daily)
        if recent:
            ctx.metric("recent_rows", len(recent))
        ctx.metric("bgd_disruption_events", len(rows(dis)))


CONNECTOR = PortWatch()
