"""News discovery: GDELT GKG (raw files), GDELT DOC API, curated RSS, ReliefWeb.

Copyright guardrail (03 §5): articles keep URL, title, a ≤ 300-character snippet and extracted
fields. Nothing here stores full text.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from cportal_core.enums import DiscoveredVia
from cportal_core.schemas.records import ArticleRecord, Record

from cportal_connectors.canonical import ParseContext, parse_ts
from cportal_connectors.decoders import rss

GDELT_LAG = timedelta(minutes=15)
_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_)")


def canonical_url(url: str) -> str:
    """Lower-case host, no fragment, no tracking parameters, no trailing slash."""
    parts = urlsplit(url.strip())
    query = "&".join(
        q for q in parts.query.split("&") if q and not _TRACKING.match(q.split("=", 1)[0])
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _hash(*parts: str | None) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


# --- GDELT GKG 2.1 (DS-NEWS-02) ----------------------------------------------------------------

_TITLE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)
_SRCLC = re.compile(r"srclc:([a-z]{3})")


def _gkg_locations(v2: str, limit: int = 12) -> list[dict[str, Any]]:
    """V2Locations: 'type#name#country#adm1#adm2#lat#lon#featureid#offset;…'."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in v2.split(";"):
        f = block.split("#")
        if len(f) < 8 or f[1] in seen:
            continue
        seen.add(f[1])
        try:
            lat, lon = float(f[5]), float(f[6])
        except ValueError:
            continue
        out.append(
            {"type": int(f[0] or 0), "name": f[1], "country_fips": f[2], "lat": lat, "lon": lon}
        )
        if len(out) >= limit:
            break
    return out


def _gkg_themes(v2: str, limit: int = 40) -> list[str]:
    """V2Themes: 'THEME,offset;…' → distinct theme names in first-mention order."""
    themes: dict[str, None] = {}
    for block in v2.split(";"):
        name = block.split(",", 1)[0]
        if name:
            themes.setdefault(name, None)
    return list(themes)[:limit]


def parse_gdelt_gkg(body: bytes, ctx: ParseContext, columns: list[str]) -> list[Record]:
    """GKG rows (tab-separated, no header). Only web documents (collection 1) become articles."""
    index = {c: i for i, c in enumerate(columns)}
    out: list[Record] = []
    for line in body.decode("utf-8", "replace").splitlines():
        row = line.split("\t")
        if len(row) != len(columns) or row[index["SourceCollectionIdentifier"]] != "1":
            continue
        url = row[index["DocumentIdentifier"]]
        seen = datetime.strptime(row[index["DATE"]], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        title_match = _TITLE.search(row[index["Extras"]])
        lang_match = _SRCLC.search(row[index["TranslationInfo"]])
        tone = row[index["V2Tone"]].split(",")[0]
        out.append(
            ArticleRecord(
                id=ctx.rid("article", canonical_url(url)),
                **ctx.lineage(row[index["GKGRECORDID"]], available_at=seen + GDELT_LAG),
                url=url,
                url_canonical=canonical_url(url),
                source_name=row[index["SourceCommonName"]] or None,
                published_at=seen,
                lang="en",  # GKG English stream, or GDELT's machine translation into English
                source_lang=lang_match.group(1) if lang_match else "eng",
                title=html.unescape(title_match.group(1).strip()) if title_match else None,
                content_hash=_hash(canonical_url(url)),
                discovered_via=DiscoveredVia.GDELT_GKG,
                gdelt_ids=[row[index["GKGRECORDID"]]],
                themes=_gkg_themes(row[index["V2Themes"]]),
                locations=_gkg_locations(row[index["V2Locations"]]),
                tone=float(tone) if tone else None,
            )
        )
    return out


# --- GDELT DOC 2.0 (DS-NEWS-01) -------------------------------------------------------------------


def parse_gdelt_doc(body: bytes, ctx: ParseContext) -> list[Record]:
    """`mode=ArtList&format=json`: {"articles": [{url, title, seendate, domain, language,
    sourcecountry}]}. No real sample exists (429 from this network, A-013); the format is
    from the DOC 2.0 documentation and the synthetic twin renders it."""
    out: list[Record] = []
    for a in json.loads(body).get("articles", []):
        url = a.get("url")
        if not url:
            continue
        seen = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        out.append(
            ArticleRecord(
                id=ctx.rid("article", canonical_url(url)),
                **ctx.lineage(canonical_url(url), available_at=seen),
                url=url,
                url_canonical=canonical_url(url),
                source_name=a.get("domain"),
                published_at=seen,
                lang=(a.get("language") or "")[:8] or None,
                source_lang=(a.get("language") or "")[:8] or None,
                title=a.get("title"),
                content_hash=_hash(canonical_url(url)),
                discovered_via=DiscoveredVia.GDELT_DOC,
                locations=[{"country_fips": a["sourcecountry"]}] if a.get("sourcecountry") else [],
            )
        )
    return out


# --- RSS (DS-NEWS-03) -----------------------------------------------------------------------------


def parse_rss(body: bytes, ctx: ParseContext, feed_id: str) -> list[Record]:
    """Raw RSS/Atom XML (live) or the harness's decoded JSON (committed samples) — the same
    structure either way: {feed, items: [{id, link, title, published, tags, snippet}]}."""
    doc = json.loads(body) if body.lstrip()[:1] == b"{" else rss(body)
    out: list[Record] = []
    for item in doc.get("items", []):
        url = item.get("link") or item.get("id")
        if not url:
            continue
        published = parse_ts(item.get("published") or item.get("updated"))
        out.append(
            ArticleRecord(
                id=ctx.rid("article", canonical_url(url)),
                **ctx.lineage(item.get("id") or url, available_at=published or ctx.fetched_at),
                url=url,
                url_canonical=canonical_url(url),
                source_name=(doc.get("feed") or {}).get("title"),
                published_at=published,
                title=item.get("title"),
                snippet=item.get("snippet"),
                content_hash=_hash(canonical_url(url), item.get("title")),
                discovered_via=DiscoveredVia.RSS,
                feed_id=feed_id,
                themes=[t for t in item.get("tags") or [] if isinstance(t, str)][:20],
            )
        )
    return out


# --- ReliefWeb (DS-NEWS-04) -----------------------------------------------------------------------


def parse_reliefweb_reports(body: bytes, ctx: ParseContext) -> list[Record]:
    out: list[Record] = []
    for item in json.loads(body).get("data", []):
        f = item.get("fields") or {}
        url = f.get("url_alias") or item.get("href")
        if not url:
            continue
        created = parse_ts((f.get("date") or {}).get("created"))
        published = parse_ts((f.get("date") or {}).get("original")) or created
        sources = [s.get("shortname") for s in f.get("source") or [] if s.get("shortname")]
        languages = [x.get("code") for x in f.get("language") or [] if x.get("code")]
        out.append(
            ArticleRecord(
                id=ctx.rid("article", canonical_url(url)),
                **ctx.lineage(item.get("id"), available_at=created),
                url=url,
                url_canonical=canonical_url(url),
                source_name=", ".join(sources) or "ReliefWeb",
                published_at=published,
                lang=languages[0] if languages else None,
                source_lang=languages[0] if languages else None,
                title=f.get("title"),
                content_hash=_hash(canonical_url(url)),
                discovered_via=DiscoveredVia.RELIEFWEB,
                themes=[d.get("name") for d in f.get("disaster_type") or [] if d.get("name")]
                + [d.get("name") for d in f.get("disaster") or [] if d.get("name")],
                locations=[
                    {"iso3": c.get("iso3")} for c in f.get("country") or [] if c.get("iso3")
                ],
            )
        )
    return out
