"""Real anchorage waits and berth times at Chattogram from C4's split (GFW arrivals + CPA berth
stays, A-114), cached for 10 minutes: the query joins a few thousand visits (~100–250 ms)."""

from __future__ import annotations

import time
from typing import Any

from cportal_c4 import service as c4
from sqlalchemy.orm import Session

TTL_S = 600.0
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def berth_waits(session: Session, locode: str = "BDCGP") -> dict[str, Any] | None:
    hit = _cache.get(locode)
    if hit and time.monotonic() - hit[0] < TTL_S:
        return hit[1]
    value = c4.wait_stats(session, locode)
    _cache[locode] = (time.monotonic(), value)
    return value


def describe(s: dict[str, Any]) -> str:
    return (
        f"median of {s['n']} real berthings, {s['from']:%d %b} – {s['to']:%d %b %Y} "
        f"(GFW arrival → CPA berthing)"
    )
