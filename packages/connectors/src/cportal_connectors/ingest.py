"""Load sources into Postgres through their parsers: `uv run ingest --replay all`.

Replay mode parses the committed samples (02 §8), so the database fills with real data offline.
Each source run is recorded in `ingestion_run`; `data_source` mirrors the registry. Sources load
in dependency order (places and ports before the rows that reference them).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from cportal_core.db import session_scope
from cportal_core.enums import DataMode, RunStatus
from cportal_core.ids import stable_id
from cportal_core.loader import upsert
from cportal_core.models import DataSource, IngestionRun
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cportal_connectors.registry import connectors, registry

# Reference data first; everything else may point at its rows.
LOAD_ORDER = [
    "DS-PORT-05",
    "DS-GEO-01",
    "DS-GEO-04",
    "DS-GEO-02",
    "DS-PORT-08",
    "DS-PORT-06",
    "DS-PORT-07",
    "DS-PORT-01",
    "DS-AIS-02",
    "DS-SAT-04",
    "DS-AIS-01",
]


def ordered(ds_ids: Sequence[str]) -> list[str]:
    first = [d for d in LOAD_ORDER if d in ds_ids]
    return first + sorted(d for d in ds_ids if d not in first)


def sync_data_sources(session: Session) -> int:
    """Mirror config/sources.yaml into `data_source` for the Data & Models page."""
    rows = []
    for ds_id, entry in registry().items():
        rows.append(
            {
                "id": stable_id("data_source", ds_id),
                "ds_id": ds_id,
                "name": str(entry.get("name", ds_id))[:200],
                "tier": str(entry.get("tier", "P2")),
                "status": str(entry.get("status", "unprobed")),
                "default_mode": str(entry.get("mode")) if entry.get("mode") else None,
                "fallback": str(entry.get("fallback")) if entry.get("fallback") else None,
                "nc": bool(entry.get("nc", False)),
                "source_id": "registry",
                "data_mode": DataMode.REPLAY.value,
                "is_synthetic": False,
            }
        )
    stmt = insert(DataSource).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            c: stmt.excluded[c]
            for c in ("name", "tier", "status", "default_mode", "fallback", "nc")
        },
    )
    session.execute(stmt)
    return len(rows)


def replay_source(session: Session, ds_id: str) -> dict[str, int]:
    connector = connectors()[ds_id]
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    run = IngestionRun(
        source_id=ds_id,
        data_mode=DataMode.REPLAY.value,
        is_synthetic=False,
        started_at=started,
        status=RunStatus.RUNNING.value,
    )
    session.add(run)
    session.flush()
    counts = upsert(session, connector.replay())
    run.status = RunStatus.SUCCEEDED.value
    run.records = sum(counts.values())
    run.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    run.ended_at = datetime.now(UTC)
    run.notes = {"tables": counts}
    session.execute(
        update(DataSource).where(DataSource.ds_id == ds_id).values(last_success_ts=run.ended_at)
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__.split("\n")[0])
    parser.add_argument("ds_ids", nargs="*", help="DS-IDs, or 'all' (default: all with parsers)")
    parser.add_argument("--replay", action="store_true", help="parse committed samples (offline)")
    parser.add_argument("--database-url", help="override DATABASE_URL")
    args = parser.parse_args(argv)
    if not args.replay:
        parser.error("only --replay exists in M1; live fetching arrives with the M2 worker")
    available = [d for d, c in connectors().items() if c.parsers]
    wanted = available if not args.ds_ids or args.ds_ids == ["all"] else args.ds_ids
    unknown = sorted(set(wanted) - set(available))
    if unknown:
        parser.error(f"no parsers for {', '.join(unknown)}")
    with session_scope(args.database_url) as session:
        print(f"data_source rows: {sync_data_sources(session)}")
    failed = 0
    for ds_id in ordered(wanted):
        try:
            with session_scope(args.database_url) as session:
                t0 = time.perf_counter()
                counts = replay_source(session, ds_id)
            summary = ", ".join(f"{t}={n}" for t, n in counts.items())
            print(f"{ds_id:13} {time.perf_counter() - t0:5.1f}s  {summary}")
        except Exception as exc:  # report and continue: one bad source must not block others
            failed += 1
            message = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
            print(f"{ds_id:13} FAILED {message}")
            with session_scope(args.database_url) as session:  # the failed transaction is gone
                session.add(
                    IngestionRun(
                        source_id=ds_id,
                        data_mode=DataMode.REPLAY.value,
                        is_synthetic=False,
                        status=RunStatus.FAILED.value,
                        errors=1,
                        ended_at=datetime.now(UTC),
                        notes={"error": message},
                    )
                )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
