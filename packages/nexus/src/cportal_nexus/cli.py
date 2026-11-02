"""`uv run nexus backtest`: score the Nexus alert rule against real port data (NX-AC06)."""

from __future__ import annotations

import argparse
import json
import sys

from cportal_core.db import session_scope
from cportal_core.paths import repo_root

from cportal_nexus import backtest

REPORT = repo_root() / "docs" / "model-cards" / "nexus-backtest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nexus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backtest", help="K-03 lead time and K-04 precision on real port data")
    args = ap.parse_args(argv)
    if args.cmd == "backtest":
        with session_scope() as session:
            report = backtest.run(session)
        REPORT.write_text(json.dumps(report, indent=1, default=str) + "\n")
        k03 = report.get("k03_lead_time_h", {})
        print(
            f"window {report['window']['start']} → {report['window']['end']}: "
            f"{report['alerts']} alerts, {report['episodes']} port-data episodes; "
            f"K-04 precision {report['k04_precision']}, recall {report['recall']}, "
            f"K-03 lead median {k03.get('median')} h (n {k03.get('n')}); "
            f"misses explained {report['missed_explained']} → {REPORT.name}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
