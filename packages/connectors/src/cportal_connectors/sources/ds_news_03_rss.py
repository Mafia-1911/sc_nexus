"""DS-NEWS-03 · Curated RSS feeds (config/feeds.yaml): Bangladesh and industry coverage.

Committed samples keep metadata and ≤ 300-character snippets only (news-copyright guardrail,
03-data-sources.md §5); the verbatim feeds stay in the gitignored raw zone.
"""

from __future__ import annotations

import html
import json
import re
import time
from datetime import UTC, datetime
from functools import partial
from typing import Any
from urllib.parse import urlsplit

import yaml
from cportal_core.paths import config_dir
from cportal_core.schemas.records import ArticleRecord, Record

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import rss
from cportal_connectors.harness import ProbeContext
from cportal_connectors.live import LiveError, LiveHttp
from cportal_connectors.parsers.news import parse_rss

SNIPPET_CHARS = 300
BD_TERMS = re.compile(r"(?i)bangladesh|chattogram|chittagong|dhaka|mongla|payra|\bRMG\b|garment")
PORT_TERMS = re.compile(r"(?i)\bport\b|vessel|container|shipping|freight|congestion|berth")
_TAG = re.compile(r"<[^>]+>")


def snippet(text: str | None) -> str:
    plain = " ".join(html.unescape(_TAG.sub(" ", text or "")).split())
    return plain if len(plain) <= SNIPPET_CHARS else plain[: SNIPPET_CHARS - 1] + "…"


def metadata_only(body: bytes) -> bytes:
    """Reduce a feed to the fields we may keep: id, link, title, dates, a short snippet."""
    parsed = rss(body)
    items = [
        {
            "id": e.get("id"),
            "link": e.get("link"),
            "title": e.get("title"),
            "published": e.get("published_parsed") or e.get("published"),
            "updated": e.get("updated_parsed") or e.get("updated"),
            "authors": [a.get("name") for a in e.get("authors", []) if isinstance(a, dict)],
            "tags": [t.get("term") for t in e.get("tags", []) if isinstance(t, dict)],
            "snippet": snippet(e.get("summary")),
            "has_full_content": bool(e.get("content")),
        }
        for e in parsed["entries"]
    ]
    feed = {k: parsed["feed"].get(k) for k in ("title", "link", "language", "updated")}
    return json.dumps({"feed": feed, "items": items}, ensure_ascii=False, indent=1).encode()


def feeds() -> list[dict[str, Any]]:
    with (config_dir() / "feeds.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    entries: list[dict[str, Any]] = data["feeds"]
    return entries


def _when(entry: dict[str, Any]) -> str | None:
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    return value if isinstance(value, str) else None


class CuratedRss(Connector):
    ds_id = "DS-NEWS-03"
    title = "Curated RSS feeds"
    live_every_min = 30
    parsers = {
        f"feed_{feed}.json": partial(parse_rss, feed_id=feed)
        for feed in (
            "container_news",
            "daily_star_business",
            "daily_star_top",
            "dhaka_tribune",
            "fda_press",
            "gcaptain",
            "hellenic_shipping",
            "just_style",
            "loadstar",
            "splash247",
            "tbs_economy",
            "tbs_top",
            "textile_today",
        )
    }
    record_types = (ArticleRecord,)
    field_notes = {
        "feed_daily_star_business:entries[].link": FieldNote("", "Canonical article URL"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        last_hit: dict[str, float] = {}
        per_feed: dict[str, Any] = {}
        for feed in feeds():
            if feed["status"] != "active":
                per_feed[feed["id"]] = {"status": feed["status"], "note": feed.get("note")}
                continue
            host = urlsplit(feed["url"]).netloc
            delay = float(feed.get("crawl_delay_s", 0))
            if host in last_hit and (wait := delay - (time.monotonic() - last_hit[host])) > 0:
                time.sleep(wait)
            result = ctx.http(
                ProbeCall(
                    f"feed_{feed['id']}",
                    feed["url"],
                    decode=rss,
                    records="entries[]",
                    ext="xml",
                    sample=True,
                    sample_transform=metadata_only,
                    sample_ext="json",
                )
            )
            last_hit[host] = time.monotonic()
            per_feed[feed["id"]] = self._feed_stats(result.parsed, result.status)
        ctx.http(
            ProbeCall(
                "missing_feed", "https://gcaptain.com/feed-does-not-exist/", "bad_param", decode=rss
            )
        )
        ctx.http(
            ProbeCall("client_timeout", "https://gcaptain.com/feed/", "timeout", timeout_s=0.001)
        )
        ctx.metric("feeds", per_feed)
        active = [v for v in per_feed.values() if isinstance(v, dict) and "items" in v]
        ctx.metric("items_total", sum(v["items"] for v in active))
        ctx.metric("items_mentioning_bangladesh", sum(v["bd_items"] for v in active))

    @staticmethod
    def _feed_stats(doc: Any, status: int | None) -> dict[str, Any]:
        if not isinstance(doc, dict):
            return {"http": status, "parsed": False}
        entries = doc.get("entries", [])
        dates = sorted(d for d in (_when(e) for e in entries) if d)
        now = datetime.now(UTC)
        newest_age_h = None
        if dates:
            newest_age_h = round(
                (now - datetime.fromisoformat(dates[-1])).total_seconds() / 3600, 1
            )
        text = [f"{e.get('title', '')} {e.get('summary', '')}" for e in entries]
        return {
            "http": status,
            "format": doc.get("version"),
            "bozo": doc.get("bozo"),
            "items": len(entries),
            "oldest": dates[0] if dates else None,
            "newest": dates[-1] if dates else None,
            "newest_age_hours": newest_age_h,
            "bd_items": sum(bool(BD_TERMS.search(t)) for t in text),
            "port_items": sum(bool(PORT_TERMS.search(t)) for t in text),
            "full_content_items": sum(bool(e.get("content")) for e in entries),
            "language": (doc.get("feed") or {}).get("language"),
        }

    def live(self, http: LiveHttp) -> list[Record]:
        """Every active feed, honouring robots.txt crawl delays. Only metadata and ≤ 300-char
        snippets are archived and parsed (03 §5). One dead feed does not fail the source."""
        out: list[Record] = []
        errors: list[str] = []
        active = [f for f in feeds() if f["status"] == "active"]
        last_hit: dict[str, float] = {}
        for feed in active:
            host = urlsplit(feed["url"]).netloc
            delay = float(feed.get("crawl_delay_s", 0))
            if host in last_hit and (wait := delay - (time.monotonic() - last_hit[host])) > 0:
                time.sleep(wait)
            try:
                body = http.get(
                    f"feed_{feed['id']}", feed["url"], ext="json", archive_transform=metadata_only
                )
            except LiveError as exc:
                errors.append(str(exc))
                continue
            finally:
                last_hit[host] = time.monotonic()
            out += parse_rss(metadata_only(body), http.ctx(), feed_id=feed["id"])
        if active and len(errors) == len(active):
            raise LiveError("; ".join(errors))
        return out


CONNECTOR = CuratedRss()
