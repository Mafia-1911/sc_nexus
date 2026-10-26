"""`uv run seed`: load the reference replay and the synthetic scenarios into Postgres.

1. Real reference data first: every source with a parser, replayed from committed samples
   (same as `uv run ingest --replay all`), so worlds can point at real ports, berths and lanes.
2. Each scenario: world, port DES history, source twins, scenario events and projection KPIs,
   upserted in one transaction per scenario. Re-running is idempotent (deterministic ids).

G1 target: the synthetic world seeds in < 60 s.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime

from cportal_connectors import ingest
from cportal_connectors.canonical import scenario_uuid
from cportal_core.db import session_scope
from cportal_core.enums import DataMode, RunStatus
from cportal_core.loader import upsert
from cportal_core.models import IngestionRun

from cportal_sim.scenarios import build_scenario

DEFAULT_SCENARIOS = ("baseline", "cyclone_supplier_delay")


def seed_scenario(key: str, database_url: str | None = None) -> dict[str, int]:
    t0 = time.perf_counter()
    run = build_scenario(key)
    built = time.perf_counter() - t0
    with session_scope(database_url) as session:
        counts = upsert(session, run.records)
        session.add(
            IngestionRun(
                source_id="sim",
                data_mode=DataMode.SYNTHETIC.value,
                is_synthetic=True,
                scenario_id=scenario_uuid(key),
                generator_version="cportal-sim/0.1.0",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
                records=sum(counts.values()),
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                notes={
                    "tables": counts,
                    "build_s": round(built, 2),
                    "hero": json.loads(json.dumps(run.world.hero, default=str)),
                },
            )
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--scenario",
        action="append",
        help=f"scenario key (repeatable; default: {', '.join(DEFAULT_SCENARIOS)})",
    )
    parser.add_argument("--skip-reference", action="store_true", help="skip the replay step")
    parser.add_argument("--database-url", help="override DATABASE_URL")
    args = parser.parse_args(argv)
    t0 = time.perf_counter()
    if not args.skip_reference:
        argv_ingest = ["--replay", "all"]
        if args.database_url:
            argv_ingest += ["--database-url", args.database_url]
        if ingest.main(argv_ingest) != 0:
            print("reference replay had failures; continuing with the scenarios")
    failed = 0
    for key in args.scenario or DEFAULT_SCENARIOS:
        t1 = time.perf_counter()
        try:
            counts = seed_scenario(key, args.database_url)
        except Exception as exc:  # one line, not the full SQL statement
            failed += 1
            detail = str(getattr(exc, "orig", exc)).splitlines()
            print(f"scenario {key:24} FAILED {type(exc).__name__}: {' | '.join(detail[:2])}")
            continue
        total = sum(counts.values())
        print(f"scenario {key:24} {time.perf_counter() - t1:5.1f}s  {total} rows")
    elapsed = time.perf_counter() - t0
    print(f"seeded in {elapsed:.1f}s (G1 target < 60 s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
