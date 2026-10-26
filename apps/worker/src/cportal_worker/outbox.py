"""Outbox consumer and job runner (ADR-004).

Pending `outbox_event` rows are claimed with `FOR UPDATE SKIP LOCKED`, dispatched to idempotent
handlers and marked processed; failures retry up to MAX_ATTEMPTS, then stay recorded as dead
letters. `job.queued` events run jobs. Capabilities that do not exist yet fail their jobs with
an honest message instead of pretending to succeed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cportal_core.db import session_scope
from cportal_core.enums import JobStatus
from cportal_core.models import Job, OutboxEvent
from sqlalchemy import select

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
NOT_YET = {
    "c1.what_if": "C1 what-if arrives in M3 (Supplier Network).",
    "c2.extract": "C2 extraction arrives in M4 (Disruption Radar).",
    "c3.plan": "C3 route planning arrives in M5 (Route Planner).",
    "c5.inspect": "C5 inspection arrives in M7 (Quality Lab).",
}


def run_scenario(params: dict[str, Any], database_url: str | None) -> dict[str, Any]:
    from cportal_sim.seed import seed_scenario  # heavy import, only when a job needs it

    counts = seed_scenario(str(params["scenario"]), database_url)
    return {"rows": sum(counts.values()), "tables": counts}


JOB_HANDLERS: dict[str, Callable[[dict[str, Any], str | None], dict[str, Any]]] = {
    "scenario.run": run_scenario,
}


def run_job(job_id: UUID, database_url: str | None = None) -> str:
    with session_scope(database_url) as session:
        job = session.get(Job, job_id)
        if job is None or job.status != JobStatus.QUEUED.value:
            return "skipped"  # idempotent: already handled
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        kind, params = job.kind, dict(job.params)
    handler = JOB_HANDLERS.get(kind)
    result: dict[str, Any] = {}
    error: str | None = None
    if handler is None:
        error = NOT_YET.get(kind, f"no handler for job kind {kind!r}")
    else:
        try:
            result = handler(params, database_url)
        except Exception as exc:  # recorded on the job; the worker keeps running
            error = f"{type(exc).__name__}: {exc}"[:1000]
    with session_scope(database_url) as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = JobStatus.FAILED.value if error else JobStatus.SUCCEEDED.value
        job.error = error
        job.result = result
        job.progress = 1.0
        job.finished_at = datetime.now(UTC)
        return job.status


def _dispatch(event: OutboxEvent, database_url: str | None) -> None:
    if event.topic == "job.queued":
        run_job(UUID(str(event.payload["job_id"])), database_url)
    # source.ingested / source.degraded: read by the UI from data_source; feature refresh and
    # alerting subscribe here from M3 on.


def drain(database_url: str | None = None, batch: int = 20) -> int:
    """Process pending events oldest first. Returns how many were handled."""
    handled = 0
    while True:
        with session_scope(database_url) as session:
            events = session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
                .order_by(OutboxEvent.created_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            ).all()
            if not events:
                return handled
            for event in events:
                try:
                    _dispatch(event, database_url)
                    event.processed_at = datetime.now(UTC)
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                    log.exception("outbox handler failed", extra={"topic": event.topic})
                handled += 1
