"""`uv run c4 train [BDCGP]`: backtest C4 on real GFW calls and store the replay predictions."""

from __future__ import annotations

import argparse
import json
import sys

from cportal_core.db import session_scope
from cportal_core.paths import repo_root

from cportal_c4 import pipeline, store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c4", description=__doc__.split("\n")[0])
    parser.add_argument("--database-url")
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="train, evaluate and store replay predictions")
    t.add_argument("locode", nargs="?", default="BDCGP")
    t.add_argument("--no-ablation", action="store_true", help="skip the feed-latency ablation")
    t.add_argument("--dry-run", action="store_true", help="evaluate only; write nothing")
    args = parser.parse_args(argv)
    with session_scope(args.database_url) as session:
        run = pipeline.train(session, args.locode, ablation=not args.no_ablation)
        out = repo_root() / "docs" / "model-cards" / f"c4-eval-{args.locode}.json"
        out.write_text(json.dumps(run.report, indent=1) + "\n")
        print(json.dumps({k: run.report[k] for k in ("split", "dwell", "remaining")}, indent=1))
        print(json.dumps(run.report.get("queue"), indent=1))
        if not args.dry_run:
            print(store.refresh(session, run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
