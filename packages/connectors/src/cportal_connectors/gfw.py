"""Global Fishing Watch API v3 helpers shared by DS-AIS-02 and DS-SAT-04.

Docs (read 2026-10-26): Bearer token; 50,000 requests/day and 1,500,000/month, and exceeding
either blocks every token on the account (24 h / 30 days) with HTTP 429. 4Wings runs one report
at a time per user (a second gets 429) and may answer 524 after 100 s, in which case the result
is fetched from /4wings/last-report. Licence CC BY-NC 4.0, non-commercial only.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from typing import Any

from cportal_core.areas import BBox

from cportal_connectors.base import ProbeCall, Purpose
from cportal_connectors.harness import CallResult, ProbeContext

API = "https://gateway.api.globalfishingwatch.org/v3"
PORT_VISITS = "public-global-port-visits-events:latest"
PRESENCE = "public-global-presence:latest"
SAR = "public-global-sar-presence:latest"
IDENTITY = "public-global-vessel-identity:latest"


def auth(ctx: ProbeContext) -> dict[str, str]:
    token = ctx.secret("GFW_API_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def polygon(box: BBox) -> dict[str, Any]:
    ring = [
        [box.lon_min, box.lat_min],
        [box.lon_max, box.lat_min],
        [box.lon_max, box.lat_max],
        [box.lon_min, box.lat_max],
        [box.lon_min, box.lat_min],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def feature_collection(box: BBox) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": polygon(box)}],
    }


def unzip_json(body: bytes) -> Any:
    """4Wings returns a zip with the result file and caveats; plain JSON is accepted too."""
    if body[:1] in (b"{", b"["):
        return json.loads(body)
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    result: dict[str, Any] = {"_members": sorted(members)}
    for name, data in members.items():
        if name.endswith(".json"):
            result[name] = json.loads(data)
        elif name.endswith((".csv", ".txt", ".md")):
            result[name] = data.decode("utf-8", errors="replace")[:4000]
    return result


def report(
    ctx: ProbeContext,
    name: str,
    params: dict[str, Any],
    box: BBox,
    purpose: Purpose = "main",
    note: str = "",
    sample: bool = True,
) -> CallResult:
    """POST a 4Wings report for a polygon; on 524 poll last-report a few times."""
    result = ctx.http(
        ProbeCall(
            name,
            f"{API}/4wings/report",
            purpose,
            method="POST",
            params=params,
            headers=auth(ctx),
            json_body={"geojson": feature_collection(box)},
            timeout_s=180,
            decode=unzip_json,
            ext="zip",
            sample=sample,
            note=note,
        )
    )
    for attempt in range(4):
        if result.status != 524:
            break
        time.sleep(30)
        result = ctx.http(
            ProbeCall(
                f"{name}_last_report_{attempt + 1}",
                f"{API}/4wings/last-report",
                purpose,
                headers=auth(ctx),
                timeout_s=120,
                decode=unzip_json,
                ext="zip",
                sample=sample,
                note="report exceeded 100 s (524); polling last-report",
            )
        )
    return result


def _unwrap(found: list[Any]) -> list[dict[str, Any]]:
    """4Wings `entries` are [{"<dataset>:<version>": [rows...]}, ...]; flatten to rows."""
    rows: list[dict[str, Any]] = []
    for item in found:
        if isinstance(item, dict):
            for sub in item.values():
                if isinstance(sub, list):
                    rows.extend(r for r in sub if isinstance(r, dict))
    return rows


def entries(doc: Any) -> list[dict[str, Any]]:
    """Rows of a 4Wings result: plain JSON, or the .json member of a zipped result."""
    if not isinstance(doc, dict):
        return []
    candidates = [doc] + [v for k, v in doc.items() if k.endswith(".json") and isinstance(v, dict)]
    for candidate in candidates:
        found = candidate.get("entries")
        if isinstance(found, list):
            return _unwrap(found)
    return []
