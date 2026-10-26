"""/sources: the registry with freshness (K-09) for the Data & Models page."""

from __future__ import annotations

from datetime import UTC, datetime

from cportal_core.models import DataSource
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from cportal_api.deps import SessionDep, meta
from cportal_api.schemas import Envelope, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


def _out(row: DataSource, now: datetime) -> SourceOut:
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
    )


@router.get("", response_model=Envelope[list[SourceOut]])
def list_sources(session: SessionDep) -> Envelope[list[SourceOut]]:
    now = datetime.now(UTC)
    rows = session.scalars(select(DataSource).order_by(DataSource.ds_id)).all()
    return Envelope(data=[_out(r, now) for r in rows], meta=meta(note="registry mirror"))


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
