"""`uv run c1 metrics|critical|whatif`: C1 against the database (02 §6 CLI shape)."""

from __future__ import annotations

import argparse
import sys

from cportal_core.db import session_scope

from cportal_c1 import service, store
from cportal_c1.schemas import DisruptionIn, WhatIfRequest

DEFAULT_SCENARIOS = ("baseline", "cyclone_supplier_delay")


def _metrics(args: argparse.Namespace) -> int:
    for key in args.scenario or DEFAULT_SCENARIOS:
        with session_scope(args.database_url) as session:
            scenario = store.scenario_row(session, key)
            if scenario is None:
                print(f"{key}: no such scenario (run `make seed`)")
                return 1
            written = store.refresh(session, scenario, force=args.force)
        print(f"{key}: {'up to date' if written is None else f'{written} nodes scored'}")
    return 0


def _critical(args: argparse.Namespace) -> int:
    with session_scope(args.database_url) as session:
        scenario = store.scenario_row(session, args.scenario)
        if scenario is None:
            print(f"{args.scenario}: no such scenario")
            return 1
        metrics = service.compute_metrics(store.load(session, scenario))
    for i, m in enumerate(service.rank(metrics, args.metric, args.industry)[: args.limit], 1):
        tts = "≥180" if m.tts_capped else m.tts_d
        print(
            f"{i:>2}. {m.name[:44]:44} {m.type:22} dominated ${m.dominated_value_usd:>12,.0f}"
            f"  TTS {tts} / TTR {m.ttr_d}  risk {m.risk_score} ({m.risk_band})"
        )
    return 0


def _whatif(args: argparse.Namespace) -> int:
    req = WhatIfRequest(
        disruptions=[
            DisruptionIn(
                node_id=args.node,
                duration_d=args.days,
                capacity_pct=args.capacity,
                extra_lead_time_d=args.extra_lead,
            )
        ],
        mc_runs=args.mc,
        seed=args.seed,
    )
    with session_scope(args.database_url) as session:
        scenario = store.scenario_row(session, args.scenario)
        if scenario is None:
            print(f"{args.scenario}: no such scenario")
            return 1
        result = service.what_if(store.load(session, scenario), req)
    spread = ""
    if result.revenue_at_risk_usd_p50 is not None and result.revenue_at_risk_usd_p90 is not None:
        p50, p90 = result.revenue_at_risk_usd_p50, result.revenue_at_risk_usd_p90
        spread = f" (P50 ${p50:,.0f}, P90 ${p90:,.0f})"
    print(
        f"first impact day {result.first_impact_d}, recovery day {result.recovery_d}, "
        f"TTS {result.tts_d}; {result.orders_late} orders late, "
        f"${result.revenue_at_risk_usd:,.0f} at risk{spread}"
    )
    for m in result.mitigations:
        print(f"- {m.title}: {m.detail}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c1", description=__doc__.split("\n")[0])
    parser.add_argument("--database-url")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("metrics", help="recompute node metrics when inputs changed")
    m.add_argument("--scenario", action="append")
    m.add_argument("--force", action="store_true")
    c = sub.add_parser("critical", help="print the criticality leaderboard")
    c.add_argument("--scenario", default="cyclone_supplier_delay")
    c.add_argument("--metric", default="dominance", choices=service.METRICS)
    c.add_argument("--industry", choices=("garments", "pharma"))
    c.add_argument("--limit", type=int, default=15)
    w = sub.add_parser("whatif", help="run a what-if on one node")
    w.add_argument("--scenario", default="cyclone_supplier_delay")
    w.add_argument("--node", required=True, help="facility UUID or port:LOCODE")
    w.add_argument("--days", type=float, required=True)
    w.add_argument("--capacity", type=float, default=0.0)
    w.add_argument("--extra-lead", type=float, default=0.0)
    w.add_argument("--mc", type=int, default=0)
    w.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    return {"metrics": _metrics, "critical": _critical, "whatif": _whatif}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
