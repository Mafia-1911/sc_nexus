"""Golden path compute (NX-AC01): the hero scenario end to end, offline, timed.

`uv run cportal-golden [--reset] [--scenario KEY]` recomputes, in order: C1 metrics, C5 lots,
then Nexus (fusion → alerts → recommendations → door ETA → studio) for one scenario, from the
replayed data already in the database (no network). `--reset` first clears the demo's decisions
(accepted or dismissed actions, acknowledged alerts) so the walk-through starts fresh. Exits 1
when the compute exceeds the 30 s budget (NX-R02).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from typing import Any

from cportal_c1 import store as c1_store
from cportal_c5 import pipeline as c5_pipeline
from cportal_core.db import session_scope
from cportal_core.models import Alert, Recommendation, Scenario
from cportal_nexus import alerts, buffer, fusion, studio, tracker
from sqlalchemy import delete, select, update

BUDGET_S = 30.0


def reset(key: str, database_url: str | None = None) -> dict[str, int]:
    with session_scope(database_url) as session:
        sid = session.scalar(select(Scenario.id).where(Scenario.key == key))
        decided = session.execute(
            delete(Recommendation).where(
                Recommendation.scenario_id == sid,
                Recommendation.status.in_(("accepted", "dismissed")),
            )
        )
        reopened = session.execute(
            update(Alert)
            .where(Alert.scenario_id == sid, Alert.status.in_(("ack", "snoozed")))
            .values(status="open")
        )
    return {
        "decisions_cleared": int(getattr(decided, "rowcount", 0) or 0),
        "alerts_reopened": int(getattr(reopened, "rowcount", 0) or 0),
    }


def run(key: str, database_url: str | None = None) -> list[tuple[str, float, Any]]:
    steps: list[tuple[str, float, Any]] = []

    def step(name: str, fn: Callable[[Any, Scenario], Any]) -> None:
        t0 = time.perf_counter()
        with session_scope(database_url) as session:
            scenario = session.scalar(select(Scenario).where(Scenario.key == key))
            if scenario is None:
                raise SystemExit(f"unknown scenario {key!r}; seed it first (make seed-docker)")
            out = fn(session, scenario)
        steps.append((name, time.perf_counter() - t0, out))

    step("C1 metrics", lambda s, sc: c1_store.refresh(s, sc, force=True))
    step("C5 lots, risk, impact", lambda s, sc: c5_pipeline.refresh(s, sc.id))
    step("Nexus fusion", lambda s, sc: fusion.refresh(s, sc.id, tracker.scenario_now(sc)))
    step("Nexus alerts", lambda s, sc: alerts.refresh(s, sc.id, tracker.scenario_now(sc)))
    step("Nexus recommendations", lambda s, sc: buffer.refresh(s))
    step("Nexus door ETA", lambda s, sc: tracker.refresh(s, sc.id))
    step("Nexus studio", lambda s, sc: studio.refresh(s, sc.id))
    return steps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cportal-golden")
    ap.add_argument("--scenario", default="cyclone_supplier_delay")
    ap.add_argument("--reset", action="store_true", help="clear demo decisions first")
    args = ap.parse_args(argv)
    if args.reset:
        print("reset:", reset(args.scenario))
    steps = run(args.scenario)
    total = sum(t for _, t, _ in steps)
    for name, t, out in steps:
        print(f"  {name:<24} {t:6.2f} s  {str(out)[:90]}")
    verdict = "within" if total <= BUDGET_S else "OVER"
    print(f"golden path compute: {total:.1f} s ({verdict} the {BUDGET_S:.0f} s budget, NX-AC01)")
    return 0 if total <= BUDGET_S else 1


if __name__ == "__main__":
    sys.exit(main())
