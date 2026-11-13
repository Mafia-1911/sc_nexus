"""`uv run cpa-poll --set fast|slow|daily|all`: poll CPA's public pages (DS-PORT-10) and store them.

fast (every 15 min in the worker): PCS schedule, vessels at berth, last 24 h, 24 h performance.
slow (hourly): yard occupancy and containers lying (each takes 10–25 s to build on the server).
daily: monthly berth occupancy, plus the last week of the sailed-vessel report.

`uv run cpa-backfill --form sailed --since 2023-01-01`: the date-range reports month by month,
one request at a time, `BACKFILL_GAP_S` apart; closed months already archived are re-read from
`data/raw/DS-PORT-10/<form>/` instead of fetched again.
"""

from __future__ import annotations

import argparse
import gzip
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from cportal_core.db import session_scope
from cportal_core.paths import raw_dir
from cportal_core.settings import get_settings

from cportal_connectors import cpa_store, cpa_tos

SETS = {
    "fast": ["pcs", "at_berth_container", "at_berth_breakbulk", "last24", "performance24"],
    "slow": ["yard", "lying"],
    "daily": ["berth_monthly"],
}
SETS["all"] = SETS["fast"] + SETS["slow"] + SETS["daily"]


def poll(which: str = "fast", database_url: str | None = None) -> dict[str, Any]:
    results = cpa_tos.fetch(SETS[which], get_settings().user_agent())
    pages = {
        f.page: {
            "status": f.status,
            "s": round(f.seconds, 1),
            "error": f.error,
            "rows": len(f.parsed) if f.parsed is not None else None,
        }
        for f in results
    }
    if not any(f.parsed for f in results):
        return {"pages": pages, "stored": None}
    with session_scope(database_url) as session:
        stored = cpa_store.store(session, results)
    return {"pages": pages, "stored": stored}


BACKFILL_GAP_S = 10.0
STORERS: dict[str, Callable[..., dict[str, int]]] = {
    "sailed": cpa_store.store_sailed,
    "gate": cpa_store.store_gate,
}


def months(since: date, until: date) -> list[tuple[date, date]]:
    """Month chunks; each ends on the next month's first day (the overlap day dedupes)."""
    out = []
    d = since.replace(day=1)
    while d <= until:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(d, since), min(nxt, until)))
        d = nxt
    return out


def _archived(form: str, start: date, end: date) -> str | None:
    hits = sorted((raw_dir("DS-PORT-10") / form).glob(f"{start:%Y%m%d}_{end:%Y%m%d}_*.html.gz"))
    return gzip.decompress(hits[-1].read_bytes()).decode() if hits else None


def backfill(
    form: str,
    since: date,
    until: date | None = None,
    database_url: str | None = None,
    refresh: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch (or re-read) each month of a date-range report and store it, month by month."""
    until = until or datetime.now(UTC).date()
    totals: dict[str, int] = {"months": 0, "fetched": 0, "rows": 0}
    fetched = False
    with httpx.Client(
        headers={"User-Agent": get_settings().user_agent()}, timeout=cpa_tos.TIMEOUT_S
    ) as client:
        for start, end in months(since, until):
            closed = end < until - timedelta(days=2)
            html = None if refresh or not closed else _archived(form, start, end)
            if html is not None:
                rows = cpa_tos.FORM_PARSERS[form](html)
                how = "archived"
            else:
                if fetched:
                    time.sleep(BACKFILL_GAP_S)
                f = cpa_tos.fetch_range(form, start, end, client)
                fetched = True
                totals["fetched"] += 1
                if f.parsed is None:
                    log(f"  {start} → {end}  {f.error}")
                    continue
                rows = f.parsed
                how = f"fetched {f.seconds:.1f} s"
            totals["months"] += 1
            totals["rows"] += len(rows)
            stored: dict[str, int] = {}
            if form in STORERS:
                with session_scope(database_url) as session:
                    stored = STORERS[form](session, rows)
                for k, v in stored.items():
                    totals[k] = totals.get(k, 0) + v
            log(f"  {start} → {end}  {len(rows):>4} rows  ({how})  {stored or ''}")
    return totals


def recent(form: str, days: int = 7, database_url: str | None = None) -> dict[str, Any]:
    """The last `days` days of a date-range report (the worker's daily refresh)."""
    today = datetime.now(UTC).date()
    with httpx.Client(
        headers={"User-Agent": get_settings().user_agent()}, timeout=cpa_tos.TIMEOUT_S
    ) as client:
        f = cpa_tos.fetch_range(form, today - timedelta(days=days), today, client)
    if f.parsed is None:
        return {"error": f.error}
    if form not in STORERS:
        return {"rows": len(f.parsed)}
    with session_scope(database_url) as session:
        return {"rows": len(f.parsed), **STORERS[form](session, f.parsed)}


def backfill_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cpa-backfill")
    ap.add_argument("--form", choices=sorted(cpa_tos.FORMS), default="sailed")
    ap.add_argument("--since", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--until", type=date.fromisoformat, default=None)
    ap.add_argument("--refresh", action="store_true", help="fetch closed months again")
    args = ap.parse_args(argv)
    print(backfill(args.form, args.since, args.until, refresh=args.refresh))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cpa-poll")
    ap.add_argument("--set", choices=sorted(SETS), default="fast")
    args = ap.parse_args(argv)
    out = poll(args.set)
    for page, p in out["pages"].items():
        print(
            f"  {page:<20} HTTP {p['status']}  {p['s']:>5} s  rows {p['rows']}  {p['error'] or ''}"
        )
    print("stored:", out["stored"])
    return 0 if out["stored"] else 1


if __name__ == "__main__":
    sys.exit(main())
