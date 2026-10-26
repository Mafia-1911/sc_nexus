"""/events, /alerts, /recommendations (C2 and Nexus). Event fusion and recommendations are
computed from M4/M8; the read shapes are fixed now."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cportal_core.models import Alert, DisruptionEvent, Recommendation
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.geo import geojson
from cportal_api.jobs import enqueue
from cportal_api.schemas import Envelope, EventOut, JobAccepted

router = APIRouter(tags=["events"])


def _event(e: DisruptionEvent) -> EventOut:
    return EventOut(
        id=e.id,
        type=e.type,
        subtype=e.subtype,
        title=e.title,
        status=e.status,
        severity=e.severity,
        confidence=e.confidence,
        alert_level=e.alert_level,
        start_est=e.start_est,
        end_est=e.end_est,
        locodes=e.locodes,
        country_iso3=e.country_iso3,
        geometry=geojson(e.geom),
        source_id=e.source_id,
        data_mode=e.data_mode,
    )


@router.get("/events", response_model=Envelope[list[EventOut]])
def list_events(
    session: SessionDep,
    scope: ScopeDep,
    type: Annotated[str | None, Query(description="DisruptionType, e.g. CYCLONE_STORM")] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    country: Annotated[str | None, Query(description="ISO3, e.g. BGD")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[EventOut]]:
    q = select(DisruptionEvent).where(scope.rows(DisruptionEvent))
    if type:
        q = q.where(DisruptionEvent.type == type)
    if status_:
        q = q.where(DisruptionEvent.status == status_)
    if country:
        q = q.where(DisruptionEvent.country_iso3.contains([country.upper()]))
    rows = session.scalars(
        q.order_by(DisruptionEvent.start_est.desc().nulls_last()).limit(limit)
    ).all()
    return Envelope(data=[_event(e) for e in rows], meta=meta(rows, scope))


@router.get("/events/{event_id}", response_model=Envelope[EventOut])
def get_event(event_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[EventOut]:
    row = session.scalar(
        select(DisruptionEvent).where(DisruptionEvent.id == event_id, scope.rows(DisruptionEvent))
    )
    if row is None:
        raise HTTPException(404, "event not found")
    return Envelope(data=_event(row), meta=meta([row], scope))


@router.get("/alerts", response_model=Envelope[list[dict[str, object]]])
def list_alerts(session: SessionDep, scope: ScopeDep) -> Envelope[list[dict[str, object]]]:
    rows = session.scalars(select(Alert).where(scope.rows(Alert)).limit(200)).all()
    out: list[dict[str, object]] = [
        {
            "id": str(a.id),
            "kind": a.kind,
            "severity": a.severity,
            "title": a.title,
            "status": a.status,
        }
        for a in rows
    ]
    return Envelope(data=out, meta=meta(rows, scope, note="alerts are raised from M8"))


@router.get("/recommendations", response_model=Envelope[list[dict[str, object]]])
def list_recommendations(session: SessionDep, scope: ScopeDep) -> Envelope[list[dict[str, object]]]:
    rows = session.scalars(
        select(Recommendation).where(scope.rows(Recommendation)).limit(200)
    ).all()
    out: list[dict[str, object]] = [
        {
            "id": str(r.id),
            "action_type": r.action_type,
            "status": r.status,
            "confidence": r.confidence,
        }
        for r in rows
    ]
    return Envelope(data=out, meta=meta(rows, scope, note="recommendations arrive with M8"))


@router.post("/events/extract", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def extract_events(session: SessionDep) -> JobAccepted:
    """Queue C2 triage and extraction over new articles (M4)."""
    return enqueue(session, "c2.extract", {})
