"""Shared helpers for the public Overpass API (DS-PORT-06, DS-GEO-02).

Usage policy (dev.overpass-api.de/overpass-doc/en/preface/commons.html): about 10,000 requests and
1 GB per day per user, slot-based rate limiting with HTTP 429, 504 when a query is too heavy.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlencode

from cportal_core.areas import BBox

from cportal_connectors.base import ProbeCall, Purpose
from cportal_connectors.harness import ProbeContext

INTERPRETER = "https://overpass-api.de/api/interpreter"
STATUS = "https://overpass-api.de/api/status"
# Listed on wiki.openstreetmap.org/wiki/Overpass_API as public, no rate limit.
MIRROR = "https://overpass.private.coffee/api/interpreter"


def query_call(
    name: str,
    ql: str,
    purpose: Purpose = "main",
    *,
    sample: bool = False,
    timeout_s: float = 120,
    note: str = "",
    url: str = INTERPRETER,
) -> ProbeCall:
    return ProbeCall(
        name,
        url,
        purpose,
        method="POST",
        data=urlencode({"data": ql}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        records="elements[]",
        sample=sample,
        timeout_s=timeout_s,
        note=note,
    )


def union(selectors: list[str], box: BBox, out: str = "tags center", timeout: int = 90) -> str:
    bb = box.overpass()
    body = "\n".join(f"  {s}({bb});" for s in selectors)
    return f"[out:json][timeout:{timeout}];\n(\n{body}\n);\nout {out};"


def element_counts(ctx: ProbeContext, name: str, doc: Any, keys: list[str]) -> None:
    """Record how many elements carry each tag value (e.g. seamark:type=anchorage)."""
    if not isinstance(doc, dict):
        return
    elements = doc.get("elements", [])
    counts: Counter[str] = Counter()
    for el in elements:
        tags = el.get("tags", {})
        for key in keys:
            if key in tags:
                counts[f"{key}={tags[key]}"] += 1
    ctx.metric(f"{name}_elements", len(elements))
    ctx.metric(f"{name}_by_type", dict(Counter(el.get("type") for el in elements)))
    ctx.metric(f"{name}_tag_values", dict(counts.most_common(25)))
    named = [el["tags"]["name"] for el in elements if "name" in el.get("tags", {})]
    ctx.metric(f"{name}_names_sample", sorted(set(named))[:40])


def osm3s_timestamp(doc: Any) -> str | None:
    if isinstance(doc, dict):
        return (doc.get("osm3s") or {}).get("timestamp_osm_base")
    return None
