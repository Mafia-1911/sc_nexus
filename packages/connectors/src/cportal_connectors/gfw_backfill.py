"""`uv run gfw-backfill --since 2023-01-01`: GFW port visits and anchorage presence history (C4).

The probe kept one 90-day page; C4 needs years of labelled calls. Port visits for the
Chattogram envelope and Mongla are fetched quarter by quarter (paged by `nextOffset`), and
outer-anchorage presence one 4Wings report per ≤ 366 days. Raw answers are cached under
`data/raw/DS-AIS-02/backfill/` (never committed: CC BY-NC 4.0), so a re-run spends no quota, and
every page goes through the same parsers as replay. About one request per second.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cportal_core.areas import BBox, bbox
from cportal_core.db import session_scope
from cportal_core.enums import DataMode, PortCallFlag, RunStatus
from cportal_core.loader import upsert
from cportal_core.models import IngestionRun
from cportal_core.paths import repo_root
from cportal_core.schemas.records import PortCallRecord, Record
from cportal_core.settings import get_settings

from cportal_connectors.canonical import ParseContext
from cportal_connectors.gfw import API, PORT_VISITS, PRESENCE, feature_collection, polygon
from cportal_connectors.parsers.maritime import parse_gfw_port_visits, parse_gfw_presence
from cportal_connectors.sources.ds_ais_02_gfw import ctg_envelope

DS = "DS-AIS-02"
CACHE = repo_root() / "data" / "raw" / DS / "backfill"


def windows(start: date, end: date, days: int) -> Iterator[tuple[date, date]]:
    while start < end:
        stop = min(start + timedelta(days=days), end)
        yield start, stop
        start = stop


class Gfw:
    def __init__(self, cache: Path = CACHE) -> None:
        token = get_settings().gfw_api_token
        if token is None:
            raise RuntimeError("no GFW token in .env (GFW_API_TOKEN)")
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token.get_secret_value()}",
                "User-Agent": get_settings().user_agent(),
            },
            timeout=180,
        )
        self.requests = 0

    def post(self, name: str, url: str, params: dict[str, Any], body: dict[str, Any]) -> bytes:
        path = self.cache / name
        if path.exists():
            return path.read_bytes()
        for attempt in range(2):  # two strikes (U-02)
            r = self.client.post(url, params=params, json=body)
            self.requests += 1
            time.sleep(1.0)
            if r.status_code == 524:  # 4Wings took > 100 s: the result waits at last-report
                time.sleep(30)
                r = self.client.get(f"{API}/4wings/last-report")
                self.requests += 1
            if r.status_code in (200, 201):
                path.write_bytes(r.content)
                return r.content
            if r.status_code == 429 or attempt == 1:
                raise RuntimeError(f"{name}: HTTP {r.status_code} {r.text[:160]}")
            time.sleep(10)
        raise AssertionError("unreachable")

    def visits(self, area: str, box: BBox, start: date, end: date) -> list[bytes]:
        body = {
            "datasets": [PORT_VISITS],
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "geometry": polygon(box),
        }
        pages: list[bytes] = []
        offset: int | None = 0
        while offset is not None:
            page = self.post(
                f"visits_{area}_{start}_{offset}.json",
                f"{API}/events",
                {"offset": offset, "limit": 1000},
                body,
            )
            pages.append(page)
            nxt = httpx.Response(200, content=page).json().get("nextOffset")
            offset = nxt if isinstance(nxt, int) and nxt > offset else None
        return pages

    def presence(self, area: str, box: BBox, start: date, end: date) -> bytes:
        params = {
            "spatial-resolution": "LOW",
            "temporal-resolution": "DAILY",
            "group-by": "VESSEL_ID",
            "datasets[0]": PRESENCE,
            "format": "JSON",
            "spatial-aggregation": "true",
            "date-range": f"{start},{end}",
        }
        return self.post(
            f"presence_{area}_{start}_{end}.zip",
            f"{API}/4wings/report",
            params,
            {"geojson": feature_collection(box)},
        )


def dedupe(records: list[Record]) -> list[Record]:
    """A visit spanning two windows comes back twice; keep the copy whose window holds its
    start (no `window_overlap` flag), so only visits that began before `--since` keep the flag."""
    out: dict[tuple[str, Any], Record] = {}
    for rec in records:
        key = (rec.table, rec.id)
        old = out.get(key)
        if (
            old is not None
            and isinstance(old, PortCallRecord)
            and PortCallFlag.WINDOW_OVERLAP not in old.quality_flags
        ):
            continue
        out[key] = rec
    return list(out.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gfw-backfill", description=__doc__.split("\n")[0])
    parser.add_argument("--since", type=date.fromisoformat, default=date(2023, 1, 1))
    parser.add_argument("--until", type=date.fromisoformat, default=None)
    parser.add_argument("--no-presence", action="store_true")
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    until = args.until or datetime.now(UTC).date()
    gfw = Gfw()
    ctx = ParseContext(DS, DataMode.REPLAY, fetched_at=datetime.now(UTC))
    records: list[Record] = []
    t0 = time.perf_counter()
    for area, box in (("ctg", ctg_envelope()), ("mongla", bbox("mongla"))):
        for start, end in windows(args.since, until, 91):
            for page in gfw.visits(area, box, start, end):
                records += parse_gfw_port_visits(page, ctx)
            print(f"visits {area} {start}..{end}: {len(records)} records so far", flush=True)
    if not args.no_presence:
        for start, end in windows(args.since, until, 366):
            body = gfw.presence("ctg_outer_anchorage", bbox("ctg_outer_anchorage"), start, end)
            records += parse_gfw_presence(body, ctx, area="ctg_outer_anchorage")
            print(f"presence {start}..{end}: {len(records)} records so far", flush=True)
    records = dedupe(records)
    with session_scope(args.database_url) as session:
        counts = upsert(session, records)
        session.add(
            IngestionRun(
                source_id=DS,
                data_mode=DataMode.REPLAY.value,
                is_synthetic=False,
                started_at=ctx.fetched_at,
                ended_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
                records=sum(counts.values()),
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                notes={"tables": counts, "backfill": f"{args.since}..{until}"},
            )
        )
    print(f"{gfw.requests} requests; {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
