"""DS-NEWS-04 · ReliefWeb API v2: needs a pre-approved `appname` since 1 Nov 2025."""

from __future__ import annotations

from cportal_core.schemas.records import ArticleRecord

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.news import parse_reliefweb_reports

ROOT = "https://api.reliefweb.int/v2"
API = f"{ROOT}/reports"
# Fields C2 needs: when, where, which disaster, who said it, and a link out (no body text).
REPORT_FIELDS = [
    "title",
    "date.created",
    "date.original",
    "country.iso3",
    "primary_country.iso3",
    "disaster.name",
    "disaster_type.name",
    "source.shortname",
    "url_alias",
    "origin",
    "format.name",
    "language.code",
]


class ReliefWeb(Connector):
    ds_id = "DS-NEWS-04"
    title = "ReliefWeb API v2"
    parsers = {"reports_bgd_fields.json": parse_reliefweb_reports}
    record_types = (ArticleRecord,)
    needs = ("RELIEFWEB_APPNAME",)

    def probe(self, ctx: ProbeContext) -> None:
        params = {"query[value]": "Bangladesh cyclone", "limit": 5, "sort[]": "date:desc"}
        ctx.http(ProbeCall("no_appname", API, "no_key", params=params))
        ctx.http(
            ProbeCall(
                "unapproved_appname",
                API,
                "bad_key",
                params={**params, "appname": "cportal-unapproved-probe"},
            )
        )
        if appname := ctx.secret("RELIEFWEB_APPNAME"):
            ctx.http(
                ProbeCall(
                    "reports_bgd",
                    API,
                    records="data[]",
                    params={**params, "appname": appname},
                    note="default response: id, score and title only",
                )
            )
            bgd = {
                "appname": appname,
                "filter[field]": "primary_country.iso3",
                "filter[value]": "bgd",
                "sort[]": "date.created:desc",
            }
            reports = ctx.http(
                ProbeCall(
                    "reports_bgd_fields",
                    API,
                    sample=True,
                    records="data[]",
                    params={**bgd, "limit": 20, "fields[include][]": REPORT_FIELDS},
                )
            )
            disasters = ctx.http(
                ProbeCall(
                    "disasters_bgd",
                    f"{ROOT}/disasters",
                    sample=True,
                    records="data[]",
                    params={
                        **bgd,
                        "filter[field]": "country.iso3",
                        "limit": 20,
                        "fields[include][]": [
                            "name",
                            "date.created",
                            "type.name",
                            "status",
                            "glide",
                        ],
                    },
                )
            )
            for name, result in (("reports", reports), ("disasters", disasters)):
                if isinstance(result.parsed, dict):
                    ctx.metric(f"{name}_bgd_total", result.parsed.get("totalCount"))
            rows = (
                (reports.parsed or {}).get("data", []) if isinstance(reports.parsed, dict) else []
            )
            dates = [((r.get("fields") or {}).get("date") or {}).get("created") for r in rows]
            ctx.metric("latest_report_created", max((d for d in dates if d), default=None))


CONNECTOR = ReliefWeb()
