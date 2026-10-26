"""/sources: the registry with freshness (K-09) for the Data & Models page."""

from __future__ import annotations

from datetime import UTC, datetime

from cportal_core.models import DataSource, IngestionRun
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from cportal_api.deps import SessionDep, meta
from cportal_api.schemas import Envelope, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


def _out(row: DataSource, now: datetime, records: int | None = None) -> SourceOut:
    age = (now - row.last_success_ts).total_seconds() / 3600 if row.last_success_ts else None
    return SourceOut(
        ds_id=row.ds_id,
        name=row.name,
        tier=row.tier,
        status=row.status,
        default_mode=row.default_mode,
        fallback=row.fallback,
        nc=row.nc,
        last_success_ts=row.last_success_ts,
        freshness_h=round(age, 2) if age is not None else None,
        licence=row.licence,
        cadence=row.cadence,
        effective_mode=row.effective_mode,
        failures=row.failures,
        last_error=row.last_error,
        records_last_run=records,
    )


def _latest_records(session: SessionDep) -> dict[str, int]:
    """Rows written by each source's most recent successful run."""
    latest = (
        select(IngestionRun.source_id, IngestionRun.records)
        .where(IngestionRun.status == "succeeded", IngestionRun.is_synthetic.is_(False))
        .distinct(IngestionRun.source_id)
        .order_by(IngestionRun.source_id, IngestionRun.started_at.desc())
    )
    return {source: records for source, records in session.execute(latest).all()}


@router.get("", response_model=Envelope[list[SourceOut]])
def list_sources(session: SessionDep) -> Envelope[list[SourceOut]]:
    now = datetime.now(UTC)
    rows = session.scalars(select(DataSource).order_by(DataSource.ds_id)).all()
    records = _latest_records(session)
    out = [_out(r, now, records.get(r.ds_id)) for r in rows]
    return Envelope(data=out, meta=meta(note="registry mirror"))


@router.get("/health", response_model=Envelope[list[SourceOut]])
def sources_health(session: SessionDep) -> Envelope[list[SourceOut]]:
    """Sources the demo depends on (P0) with their age; stale ones sort first."""
    now = datetime.now(UTC)
    rows = session.scalars(select(DataSource).where(DataSource.tier == "P0")).all()
    out = sorted((_out(r, now) for r in rows), key=lambda s: -(s.freshness_h or 1e9))
    return Envelope(data=out, meta=meta(note="P0 freshness (K-09)"))


@router.get("/{ds_id}", response_model=Envelope[SourceOut])
def get_source(ds_id: str, session: SessionDep) -> Envelope[SourceOut]:
    row = session.scalar(select(DataSource).where(DataSource.ds_id == ds_id))
    if row is None:
        raise HTTPException(404, f"unknown source {ds_id}")
    return Envelope(data=_out(row, datetime.now(UTC)), meta=meta())
