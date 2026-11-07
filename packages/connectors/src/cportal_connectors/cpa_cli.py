"""`uv run cpa-poll --set fast|slow|daily|all`: poll CPA's public pages (DS-PORT-10) and store them.

fast (every 15 min in the worker): PCS schedule, vessels at berth, last 24 h, 24 h performance.
slow (hourly): yard occupancy and containers lying (each takes 10–25 s to build on the server).
daily: monthly berth occupancy.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from cportal_core.db import session_scope
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
