"""DS-NEWS-01 · GDELT DOC 2.0 API: article discovery over a rolling three-month window."""

from __future__ import annotations

from collections import Counter
from typing import Any

from cportal_core.schemas.records import ArticleRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://api.gdeltproject.org/api/v2/doc/doc"
CTG_PORT = "(Chattogram OR Chittagong) port"


class GdeltDoc(Connector):
    ds_id = "DS-NEWS-01"
    title = "GDELT DOC 2.0 API"
    # No real sample (429 from this network, A-013): the contract runs on the synthetic twin,
    # which renders the documented ArtList JSON through parsers.news.parse_gdelt_doc.
    record_types = (ArticleRecord,)
    field_notes = {
        "artlist_ctg_port:url": FieldNote("", "Article URL (dedupe key, after normalisation)"),
        "artlist_ctg_port:seendate": FieldNote("YYYYMMDDTHHMMSSZ (UTC)", "When GDELT saw it"),
        "artlist_ctg_port:sourcecountry": FieldNote("", "Country of the outlet, full name"),
        "artlist_ctg_port:language": FieldNote("", "Article language, full English name"),
        "artlist_ctg_port:domain": FieldNote("", "Outlet domain"),
        "artlist_ctg_port:socialimage": FieldNote("", "Preview image URL (not stored, link only)"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        base = {"format": "json"}
        ctg = ctx.http(
            ProbeCall(
                "artlist_ctg_port",
                API,
                sample=True,
                records="articles[]",
                params={
                    **base,
                    "query": CTG_PORT,
                    "mode": "ArtList",
                    "maxrecords": 250,
                    "timespan": "7d",
                    "sort": "DateDesc",
                },
                note="articles mentioning Chattogram/Chittagong port, last 7 days",
            )
        )
        if ctg.status == 429:
            ctx.note(
                "first request answered 429 although no request had been sent for "
                "minutes; stopping instead of retrying (the limit is per IP)"
            )
            return
        ctx.http(
            ProbeCall(
                "timeline_ctg_port",
                API,
                sample=True,
                records="timeline[].data[]",
                params={**base, "query": CTG_PORT, "mode": "TimelineVolRaw", "timespan": "3m"},
                note="daily article counts over the full 3-month window",
            )
        )
        bd = ctx.http(
            ProbeCall(
                "artlist_bd_outlets",
                API,
                sample=True,
                records="articles[]",
                params={
                    **base,
                    "query": "sourcecountry:bangladesh (port OR shipping OR container "
                    "OR freight OR garment)",
                    "mode": "ArtList",
                    "maxrecords": 250,
                    "timespan": "7d",
                    "sort": "DateDesc",
                },
                note="Bangladeshi outlets, supply-chain keywords, last 7 days",
            )
        )
        ctx.http(
            ProbeCall(
                "short_keyword", API, "bad_param", params={**base, "query": "BD", "mode": "ArtList"}
            )
        )
        ctx.http(
            ProbeCall(
                "no_results",
                API,
                "empty",
                params={**base, "query": "xqzvkwpt", "mode": "ArtList", "timespan": "1d"},
            )
        )
        ctx.http(
            ProbeCall(
                "timespan_12m",
                API,
                "oversized",
                params={
                    **base,
                    "query": CTG_PORT,
                    "mode": "ArtList",
                    "maxrecords": 5,
                    "timespan": "12m",
                },
                note="documented maximum lookback is 3 months",
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                API,
                "timeout",
                timeout_s=0.001,
                params={**base, "query": CTG_PORT, "mode": "ArtList"},
            )
        )
        for name, result in (("ctg", ctg), ("bd_outlets", bd)):
            self._metrics(ctx, name, result.parsed)

    @staticmethod
    def _metrics(ctx: ProbeContext, name: str, doc: Any) -> None:
        if not isinstance(doc, dict):
            return
        articles = doc.get("articles", [])
        ctx.metric(f"{name}_articles_7d", len(articles))
        ctx.metric(f"{name}_by_language", dict(Counter(a.get("language") for a in articles)))
        ctx.metric(
            f"{name}_by_sourcecountry",
            dict(Counter(a.get("sourcecountry") for a in articles).most_common(8)),
        )
        ctx.metric(
            f"{name}_top_domains", dict(Counter(a.get("domain") for a in articles).most_common(10))
        )
        urls = [a.get("url") for a in articles]
        ctx.metric(f"{name}_duplicate_urls", len(urls) - len(set(urls)))


CONNECTOR = GdeltDoc()
