"""DS-WX-02 · GDACS API: tropical cyclone, flood and earthquake alerts (GeoJSON)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_core.areas import bbox
from cportal_core.schemas.records import DisruptionEventRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.live import LiveCall, LiveHttp
from cportal_connectors.parsers.hazards import parse_gdacs

API = "https://www.gdacs.org/gdacsapi/api"
CALLER = "cportal"  # the API's documented `caller` parameter identifies the client


def _wkt(name: str) -> str:
    b = bbox(name)
    ring = [
        (b.lon_min, b.lat_min),
        (b.lon_max, b.lat_min),
        (b.lon_max, b.lat_max),
        (b.lon_min, b.lat_max),
        (b.lon_min, b.lat_min),
    ]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


class Gdacs(Connector):
    ds_id = "DS-WX-02"
    title = "GDACS API"
    live_every_min = 60
    parsers = {"search_bgd.json": parse_gdacs, "event_remal.json": parse_gdacs}
    record_types = (DisruptionEventRecord,)
    field_notes = {
        "search_bgd:properties.alertlevel": FieldNote("", "Green / Orange / Red"),
        "search_bgd:properties.eventtype": FieldNote(
            "", "TC cyclone, FL flood, EQ earthquake, DR drought, VO volcano, WF wildfire"
        ),
        "search_bgd:properties.eventid": FieldNote("", "GDACS event ID (stable across episodes)"),
        "search_bgd:properties.episodeid": FieldNote("", "Latest episode (advisory) ID"),
        "search_bgd:properties.fromdate": FieldNote("UTC, no zone suffix", "Event start"),
        "search_bgd:properties.todate": FieldNote("UTC, no zone suffix", "Event end / last update"),
        "search_bgd:properties.severitydata.severity": FieldNote(
            "type-specific", "TC: max wind km/h; EQ: magnitude; FL: often 0"
        ),
    }

    def probe(self, ctx: ProbeContext) -> None:
        today = datetime.now(UTC).date()
        search = ctx.http(
            ProbeCall(
                "search_bgd",
                f"{API}/Events/geteventlist/search",
                sample=True,
                records="features[]",
                params={
                    "eventlist": "TC;FL;EQ",
                    "country": "Bangladesh",
                    "fromDate": "2019-01-01",
                    "toDate": today.isoformat(),
                    "pageSize": 100,
                    "pageNumber": 1,
                    "caller": CALLER,
                },
                note="all TC/FL/EQ events with Bangladesh in the affected countries since 2019",
            )
        )
        ctx.http(
            ProbeCall(
                "search_iso3",
                f"{API}/Events/geteventlist/search",
                "bad_param",
                params={
                    "eventlist": "TC",
                    "country": "BGD",
                    "fromDate": "2024-01-01",
                    "toDate": today.isoformat(),
                    "caller": CALLER,
                },
                note="is `country` a name or an ISO3 code?",
            )
        )
        ctx.http(
            ProbeCall(
                "latest_tc",
                f"{API}/Events/geteventlist/latest",
                "meta",
                params={"eventlist": "TC", "pageSize": 20, "caller": CALLER},
            )
        )
        ctx.http(
            ProbeCall(
                "events_near_ctg",
                f"{API}/Events/geteventlist/eventsbyarea",
                sample=True,
                records="features[]",
                params={
                    "geometryArea": _wkt("bay_of_bengal_approach"),
                    "days": 30,
                    "caller": CALLER,
                },
                note="events touching the Bay of Bengal approach box in the last 30 days (max 30)",
            )
        )
        remal = self._find(search.parsed, "REMAL")
        if remal:
            ctx.http(
                ProbeCall(
                    "event_remal",
                    f"{API}/Events/geteventdata",
                    sample=True,
                    params={"eventtype": "TC", "eventid": remal["eventid"], "caller": CALLER},
                    note="full event record for Cyclone Remal (May 2024)",
                )
            )
        ctx.http(
            ProbeCall(
                "bad_date",
                f"{API}/Events/geteventlist/search",
                "bad_param",
                params={"eventlist": "TC", "fromDate": "not-a-date", "caller": CALLER},
            )
        )
        ctx.http(
            ProbeCall(
                "no_events",
                f"{API}/Events/geteventlist/search",
                "empty",
                params={
                    "eventlist": "VO",
                    "country": "Bangladesh",
                    "fromDate": "2024-01-01",
                    "toDate": today.isoformat(),
                    "caller": CALLER,
                },
            )
        )
        ctx.http(
            ProbeCall(
                "page_past_end",
                f"{API}/Events/geteventlist/search",
                "last_page",
                params={
                    "eventlist": "TC;FL;EQ",
                    "country": "Bangladesh",
                    "fromDate": "2019-01-01",
                    "toDate": today.isoformat(),
                    "pageSize": 100,
                    "pageNumber": 50,
                    "caller": CALLER,
                },
            )
        )
        ctx.http(
            ProbeCall(
                "area_days_over_max",
                f"{API}/Events/geteventlist/eventsbyarea",
                "oversized",
                params={"geometryArea": _wkt("ctg_outer_anchorage"), "days": 365, "caller": CALLER},
                note="days is documented as max 30",
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{API}/Events/geteventlist/latest",
                "timeout",
                params={"eventlist": "TC", "caller": CALLER},
                timeout_s=0.001,
            )
        )
        self._metrics(ctx, search.parsed)

    @staticmethod
    def _find(doc: Any, name: str) -> dict[str, Any] | None:
        for feature in (doc or {}).get("features", []) if isinstance(doc, dict) else []:
            props = feature.get("properties", {})
            if (
                name.lower()
                in str(props.get("name", "")).lower() + str(props.get("eventname", "")).lower()
            ):
                return dict(props)
        return None

    @staticmethod
    def _metrics(ctx: ProbeContext, doc: Any) -> None:
        if not isinstance(doc, dict):
            return
        events = [f.get("properties", {}) for f in doc.get("features", [])]
        counts: dict[str, int] = {}
        for e in events:
            key = f"{e.get('eventtype')}/{e.get('alertlevel')}"
            counts[key] = counts.get(key, 0) + 1
        ctx.metric("bgd_events_since_2019", len(events))
        ctx.metric("bgd_events_by_type_alert", dict(sorted(counts.items())))
        ctx.metric(
            "bgd_tc_events",
            [
                f"{e.get('eventid')} {e.get('name') or e.get('eventname')} {e.get('alertlevel')} "
                f"{str(e.get('fromdate'))[:10]}"
                for e in events
                if e.get("eventtype") == "TC"
            ],
        )

    def live_calls(self, http: LiveHttp) -> list[LiveCall]:
        today = datetime.now(UTC).date()
        return [
            LiveCall(
                "search_bgd",
                f"{API}/Events/geteventlist/search",
                parse_gdacs,
                params={
                    "eventlist": "TC;FL;EQ",
                    "country": "Bangladesh",
                    "fromDate": (today - timedelta(days=60)).isoformat(),
                    "toDate": today.isoformat(),
                    "pageSize": 100,
                    "pageNumber": 1,
                    "caller": CALLER,
                },
            )
        ]


CONNECTOR = Gdacs()
