"""Live refreshes with the two-strikes rule (ADR-011, user directive U-02).

A refresh fetches through the source's live calls, parses with the same parsers as replay,
and upserts, in one transaction with its `ingestion_run` row and a `source.ingested` outbox
event. Two consecutive failures switch the source to its registry fallback; it is then retried
at most once per cool-down instead of being hammered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_connectors.live import LiveError, LiveHttp
from cportal_connectors.registry import connectors, min_interval_s, registry
from cportal_core.db import session_scope
from cportal_core.enums import DataMode, RunStatus
from cportal_core.loader import upsert
from cportal_core.models import DataSource, IngestionRun, OutboxEvent
from cportal_core.settings import Settings, get_settings
from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

STRIKES = 2
COOL_DOWN = timedelta(hours=6)


@dataclass(frozen=True)
class Outcome:
    ds_id: str
    status: str  # succeeded | failed | skipped
    records: int = 0
    detail: str = ""


def live_sources() -> dict[str, int]:
    """DS-ID → cadence in minutes, for sources whose registry mode is `live` and that define
    live calls."""
    out: dict[str, int] = {}
    for ds_id, connector in connectors().items():
        entry = registry().get(ds_id, {})
        if entry.get("mode") == "live" and connector.live_every_min:
            out[ds_id] = connector.live_every_min
    return out


def _state(session: Session, ds_id: str) -> DataSource | None:
    return session.scalar(select(DataSource).where(DataSource.ds_id == ds_id))


def refresh(
    ds_id: str, settings: Settings | None = None, database_url: str | None = None
) -> Outcome:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    with session_scope(database_url) as session:
        state = _state(session, ds_id)
        if state is None:
            return Outcome(ds_id, "skipped", detail="not in data_source (run `make seed`)")
        last = state.last_attempt_ts
        if state.failures >= STRIKES and last and now - last < COOL_DOWN:
            return Outcome(ds_id, "skipped", detail=f"on fallback until {last + COOL_DOWN:%H:%M}Z")
        state.last_attempt_ts = now
    http = LiveHttp(ds_id, settings, min_interval_s=min_interval_s(ds_id))
    try:
        records = connectors()[ds_id].live(http)
    except LiveError as exc:
        return _strike(ds_id, str(exc), database_url)
    finally:
        http.close()
    with session_scope(database_url) as session:
        counts = upsert(session, records)
        total = sum(counts.values())
        session.add(
            IngestionRun(
                source_id=ds_id,
                data_mode=DataMode.LIVE.value,
                is_synthetic=False,
                started_at=now,
                ended_at=datetime.now(UTC),
                status=RunStatus.SUCCEEDED.value,
                records=total,
                latency_ms=round((datetime.now(UTC) - now).total_seconds() * 1000, 1),
                notes={"tables": counts, "raw_files": [p.name for p in http.saved]},
            )
        )
        state = _state(session, ds_id)
        if state is not None:
            state.failures = 0
            state.effective_mode = DataMode.LIVE.value
            state.last_error = None
            state.last_success_ts = datetime.now(UTC)
        session.add(OutboxEvent(topic="source.ingested", payload={"ds_id": ds_id, "rows": total}))
    log.info("live refresh ok", extra={"ds_id": ds_id, "rows": total})
    return Outcome(ds_id, "succeeded", total)


def _strike(ds_id: str, error: str, database_url: str | None) -> Outcome:
    fallback = str(registry().get(ds_id, {}).get("fallback") or "replay")
    with session_scope(database_url) as session:
        state = _state(session, ds_id)
        failures = 1
        if state is not None:
            state.failures += 1
            failures = state.failures
            state.last_error = error[:1000]
            if failures >= STRIKES:
                state.effective_mode = fallback
        session.add(
            IngestionRun(
                source_id=ds_id,
                data_mode=DataMode.LIVE.value,
                is_synthetic=False,
                ended_at=datetime.now(UTC),
                status=RunStatus.FAILED.value,
                errors=1,
                notes={"error": error[:500], "strike": failures},
            )
        )
        payload: dict[str, Any] = {"ds_id": ds_id, "strike": failures, "error": error[:200]}
        if failures >= STRIKES:
            payload["fallback"] = fallback
            session.add(OutboxEvent(topic="source.degraded", payload=payload))
    log.warning("live refresh failed", extra={"ds_id": ds_id, "strike": failures})
    return Outcome(ds_id, "failed", detail=f"strike {failures}: {error}")
