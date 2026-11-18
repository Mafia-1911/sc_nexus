"""`uv run c6 refresh | rate | changes`: C6 on the host (the worker runs `refresh` itself)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from cportal_core.db import session_scope

from cportal_c6 import service, store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="c6", description="C6 tariff monitor")
    p.add_argument("--database-url")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="current flags, change detection, effective rates")
    r.add_argument("--on", type=dt.date.fromisoformat, help="date (default: today, UTC)")
    q = sub.add_parser("rate", help="effective rate breakdown for one product")
    q.add_argument("hs6")
    q.add_argument("--market", default="USA")
    q.add_argument("--origin", default="BGD")
    q.add_argument("--on", type=dt.date.fromisoformat)
    c = sub.add_parser("changes", help="latest detected changes")
    c.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)
    with session_scope(args.database_url) as session:
        if args.cmd == "refresh":
            print(json.dumps(store.refresh(session, args.on), indent=2))
        elif args.cmd == "rate":
            d = service.product(
                session, args.hs6, args.on, [args.market.upper()], [args.origin.upper()]
            )
            if d is None:
                print(f"HS {args.hs6} is not a watched product", file=sys.stderr)
                return 2
            print(d.model_dump_json(indent=2))
        else:
            for ch in service.changes(session, limit=args.limit):
                print(
                    f"{ch.detected_at:%Y-%m-%d} {ch.market} {ch.measure_ref} {ch.origin_code} "
                    f"{ch.change}: {ch.old_duty_text!r} → {ch.new_duty_text!r} ({ch.delta_pp})"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
