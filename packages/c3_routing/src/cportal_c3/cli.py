"""`uv run c3 build-graph|plan|calibrate`: C3 against the database."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cportal_core.db import session_scope
from cportal_core.paths import repo_root

from cportal_c3 import service, store
from cportal_c3.osm import extract
from cportal_c3.priors import load_priors
from cportal_c3.schemas import RouteIn


def _pbf() -> Path | None:
    found = sorted((repo_root() / "data" / "raw" / "DS-GEO-01").glob("*.osm.pbf"))
    return found[-1] if found else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c3", description=__doc__.split("\n")[0])
    parser.add_argument("--database-url")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-graph", help="corridor road graph from the Geofabrik extract")
    b.add_argument("--pbf", type=Path)
    p = sub.add_parser("plan", help="plan a route")
    p.add_argument("origin")
    p.add_argument("dest")
    p.add_argument("--hours", type=float, default=48, help="deadline: now + this many hours")
    p.add_argument("--teu", type=int, default=1)
    p.add_argument("--reefer", action="store_true")
    c = sub.add_parser("calibrate", help="fit road speeds to ORS HGV (C3-AC01)")
    c.add_argument("--write", action="store_true", help="store the factor in config/priors/c3.yaml")
    args = parser.parse_args(argv)
    if args.cmd == "build-graph":
        pbf = args.pbf or _pbf()
        if pbf is None or not pbf.exists():
            print("no extract in data/raw/DS-GEO-01/ (see docs/USER_TASKS.md)")
            return 1
        t0 = time.perf_counter()
        with session_scope(args.database_url) as session:
            n = store.save_edges(session, extract(pbf, load_priors()), pbf.stem)
        print(f"{n} road edges from {pbf.name} in {time.perf_counter() - t0:.0f} s")
        return 0
    if args.cmd == "calibrate":
        import json
        import re

        from cportal_c3.calibrate import calibrate

        with session_scope(args.database_url) as session:
            report = calibrate(service.network(session), load_priors())
        out = repo_root() / "docs" / "model-cards" / "c3-calibration.json"
        out.write_text(json.dumps(report, indent=1) + "\n")
        print({k: v for k, v in report.items() if k != "rows"})
        if args.write:
            cfg = repo_root() / "config" / "priors" / "c3.yaml"
            text = re.sub(
                r"calibration: [0-9.]+",
                f"calibration: {report['calibration_after']}",
                cfg.read_text(),
            )
            cfg.write_text(text)
        return 0
    with session_scope(args.database_url) as session:
        now = datetime.now(UTC)
        t0 = time.perf_counter()
        result = service.optimize(
            session,
            RouteIn(
                origin=args.origin,
                dest=args.dest,
                depart=now,
                deadline=now + timedelta(hours=args.hours),
                qty_teu=args.teu,
                cargo_profile="REEFER_2_8C" if args.reefer else "DRY_CONTAINER",
            ),
            save=False,
        )
        print(f"{len(result.plans)} plans in {time.perf_counter() - t0:.1f} s")
        for plan in result.plans:
            print(
                f"{'*' if plan.pareto_rank == 0 else ' '} {plan.name:28} {plan.km:6.0f} km  "
                f"P50 {plan.time_p50_h:5.1f} h  P90 {plan.time_p90_h:5.1f} h  "
                f"on time {plan.on_time_prob}  Tk {plan.cost_bdt:,.0f}  {plan.co2e_kg:,.0f} kg CO2e"
            )
            print(f"    {plan.explanation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
