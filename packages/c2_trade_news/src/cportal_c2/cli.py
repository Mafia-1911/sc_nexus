"""`uv run c2 process|llm|events`: C2 against the database."""

from __future__ import annotations

import argparse
import sys

from cportal_core.db import session_scope
from cportal_core.llm import OllamaProvider
from cportal_core.models import DisruptionEvent
from sqlalchemy import select

from cportal_c2 import service
from cportal_c2.llm import run
from cportal_c2.store import window_start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c2", description=__doc__.split("\n")[0])
    parser.add_argument("--database-url")
    parser.add_argument("--days", type=int, default=14)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("process", help="extract, cluster and store events for the window")
    llm = sub.add_parser("llm", help="ask the local LLM about the top-K articles, then process")
    llm.add_argument("--top", type=int, default=10)
    llm.add_argument("--model")
    sub.add_parser("events", help="list C2 events")
    args = parser.parse_args(argv)
    if args.cmd == "llm":
        provider = OllamaProvider(model=args.model)
        if not provider.available():
            print(f"local LLM {provider.model} not reachable at {provider.root}; rules only")
            return 1
        with session_scope(args.database_url) as session:
            print(run(session, provider, window_start(days=args.days), args.top))
    if args.cmd in ("process", "llm"):
        with session_scope(args.database_url) as session:
            print(service.process(session, days=args.days))
    if args.cmd == "events":
        with session_scope(args.database_url) as session:
            for e in session.scalars(
                select(DisruptionEvent)
                .where(DisruptionEvent.source_id == "c2")
                .order_by(DisruptionEvent.severity.desc())
            ):
                print(
                    f"{e.severity:.2f} {e.confidence:.2f} {e.type:28} {e.status:9} {e.title[:70]}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
