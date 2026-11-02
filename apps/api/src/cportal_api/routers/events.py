"""/events, /alerts, /recommendations (C2 §8, NX §4): grounded events with their evidence,
alerts raised from them, and buffer recommendations with accept / dismiss."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from cportal_core.models import (
    Alert,
    Article,
    DisruptionEvent,
    EventEntityLink,
    EventMention,
    Facility,
    Prediction,
    Recommendation,
)
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.geo import geojson
from cportal_api.jobs import enqueue
from cportal_api.schemas import (
    AlertOut,
    DecisionIn,
    Envelope,
    EventDetailOut,
    EventOut,
    JobAccepted,
    MentionOut,
    RecommendationOut,
)

router = APIRouter(tags=["events"])
FEEDS = ("DS-WX-02", "DS-PHARMA-01", "DS-PORT-01", "DS-NEWS-04")


def _first_urls(session: SessionDep, ids: list[UUID]) -> dict[UUID, str]:
    """The earliest report's URL per event (one query for the page)."""
    if not ids:
        return {}
    out: dict[UUID, str] = {}
    for eid, url in session.execute(
        select(EventMention.event_id, Article.url)
        .join(Article, Article.id == EventMention.article_id)
        .where(EventMention.event_id.in_(ids))
        .order_by(Article.published_at)
    ):
        out.setdefault(eid, url)
    return out


def _fusion(session: SessionDep, scope: ScopeDep, ids: list[UUID]) -> dict[UUID, Prediction]:
    """The Nexus fusion row for exactly this scope (the real world, or the chosen scenario)."""
    if not ids:
        return {}
    rows = session.scalars(
        select(Prediction).where(
            Prediction.capability == "nexus",
            Prediction.target_type == "event_confidence",
            Prediction.target_id.in_(ids),
            Prediction.scenario_id.is_(None)
            if scope.scenario_id is None
            else Prediction.scenario_id == scope.scenario_id,
        )
    ).all()
    return {p.target_id: p for p in rows}


def _event(
    e: DisruptionEvent,
    mentions: int = 0,
    fused: Prediction | None = None,
    url: str | None = None,
) -> EventOut:
    x = fused.explanation if fused else {}
    return EventOut(
        source_url=url or e.url,
        confidence_fused=fused.value if fused else None,
        corroboration=x.get("signals", []),
        fusion_checks=x.get("checks", []),
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
        summary=e.summary,
        duration_p50_h=e.duration_p50_h,
        duration_p90_h=e.duration_p90_h,
        first_seen=e.first_seen,
        last_updated=e.last_updated,
        mentions=mentions,
    )


def _alert(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id,
        kind=a.kind,
        severity=a.severity,
        title=a.title,
        body=a.body,
        status=a.status,
        event_id=a.event_id,
        entity_refs=a.entity_refs,
        created_at=a.created_at,
        data_mode=a.data_mode,
    )


def _by_value(r: RecommendationOut) -> float:
    """Best expected value first (08 §4)."""
    return -(r.expected_value_usd or 0.0)


def _rec(r: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        id=r.id,
        alert_id=r.alert_id,
        action_type=r.action_type,
        status=r.status,
        targets=r.target_refs,
        params=r.params,
        expected_benefit_usd=r.expected_benefit_usd,
        expected_cost_usd=r.expected_cost_usd,
        expected_value_usd=None
        if r.expected_benefit_usd is None
        else round(r.expected_benefit_usd - (r.expected_cost_usd or 0), 2),
        confidence=r.confidence,
        rationale=r.rationale,
        evidence_refs=r.evidence_refs,
        data_mode=r.data_mode,
        decided_at=r.decided_at,
        feedback=r.feedback,
    )


@router.get("/events", response_model=Envelope[list[EventOut]])
def list_events(
    session: SessionDep,
    scope: ScopeDep,
    type: Annotated[str | None, Query(description="DisruptionType, e.g. CYCLONE_STORM")] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    country: Annotated[str | None, Query(description="ISO3, e.g. BGD")] = None,
    source: Annotated[
        Literal["news", "feeds"] | None,
        Query(description="news: C2 events from articles; feeds: GDACS, openFDA, PortWatch"),
    ] = None,
    min_conf: Annotated[float, Query(ge=0, le=1)] = 0.0,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[EventOut]]:
    q = select(DisruptionEvent).where(scope.rows(DisruptionEvent))
    if scope.as_of is not None:  # real data: only what was known by the view time
        known = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
        q = q.where(known.is_(None) | (known <= min(scope.as_of, datetime.now(UTC))))
    if type:
        q = q.where(DisruptionEvent.type == type)
    if status_:
        q = q.where(DisruptionEvent.status == status_)
    if country:
        q = q.where(DisruptionEvent.country_iso3.contains([country.upper()]))
    if source == "news":
        q = q.where(DisruptionEvent.source_id == "c2")
    elif source == "feeds":
        q = q.where(DisruptionEvent.source_id.in_(FEEDS))
    if min_conf:
        q = q.where(DisruptionEvent.confidence >= min_conf)
    if since:
        q = q.where(DisruptionEvent.last_updated >= since)
    rows = session.scalars(
        q.order_by(DisruptionEvent.start_est.desc().nulls_last()).limit(limit)
    ).all()
    counts = dict(
        session.execute(
            select(EventMention.event_id, func.count())
            .where(EventMention.event_id.in_([e.id for e in rows]))
            .group_by(EventMention.event_id)
        ).all()
    )
    fused = _fusion(session, scope, [e.id for e in rows])
    urls = _first_urls(session, [e.id for e in rows])
    return Envelope(
        data=[_event(e, counts.get(e.id, 0), fused.get(e.id), urls.get(e.id)) for e in rows],
        meta=meta(rows, scope),
    )


@router.get("/events/{event_id}", response_model=Envelope[EventDetailOut])
def get_event(event_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[EventDetailOut]:
    """One event with every mention's text and the evidence spans the UI highlights (C2 §9)."""
    row = session.scalar(
        select(DisruptionEvent).where(DisruptionEvent.id == event_id, scope.rows(DisruptionEvent))
    )
    if row is None:
        raise HTTPException(404, "event not found")
    pairs = session.execute(
        select(EventMention, Article)
        .join(Article, Article.id == EventMention.article_id)
        .where(EventMention.event_id == event_id)
        .order_by(Article.published_at)
    ).all()
    mentions = [
        MentionOut(
            article_id=a.id,
            url=a.url,
            outlet=a.source_name,
            published_at=a.published_at,
            text=str(m.extracted.get("text") or _text(a)),
            evidence=m.evidence_spans,
            extractor=m.extractor_version,
            confidence=m.extraction_confidence,
            llm_agrees=m.extracted.get("llm_agrees"),
        )
        for m, a in pairs
    ]
    linked = [
        {"facility_id": str(f.id), "name": f.name, "cluster": f.cluster, "method": link.link_method}
        for link, f in session.execute(
            select(EventEntityLink, Facility)
            .join(Facility, Facility.id == EventEntityLink.entity_id)
            .where(EventEntityLink.event_id == event_id, scope.rows(EventEntityLink))
        )
    ]
    alerts = session.scalars(select(Alert).where(Alert.event_id == event_id, scope.rows(Alert)))
    alert_rows = list(alerts)
    recs = session.scalars(
        select(Recommendation).where(
            Recommendation.alert_id.in_([a.id for a in alert_rows]), scope.rows(Recommendation)
        )
    ).all()
    return Envelope(
        data=EventDetailOut(
            event=_event(
                row,
                len(mentions),
                _fusion(session, scope, [row.id]).get(row.id),
                mentions[0].url if mentions else None,
            ),
            mentions=mentions,
            linked_facilities=linked,
            alerts=[_alert(a) for a in alert_rows],
            recommendations=sorted((_rec(r) for r in recs), key=_by_value),
        ),
        meta=meta([row], scope),
    )


def _text(a: Article) -> str:
    from cportal_c2.extract import article_text

    return article_text(a.title, a.snippet)


@router.get("/alerts", response_model=Envelope[list[AlertOut]])
def list_alerts(
    session: SessionDep,
    scope: ScopeDep,
    status_: Annotated[str | None, Query(alias="status")] = "open",
) -> Envelope[list[AlertOut]]:
    q = select(Alert).where(scope.rows(Alert))
    if status_:
        q = q.where(Alert.status == status_)
    rows = session.scalars(q.order_by(Alert.created_at.desc()).limit(200)).all()
    return Envelope(data=[_alert(a) for a in rows], meta=meta(rows, scope))


@router.post("/alerts/{alert_id}/ack", response_model=Envelope[AlertOut])
def ack_alert(alert_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[AlertOut]:
    row = session.scalar(select(Alert).where(Alert.id == alert_id, scope.rows(Alert)))
    if row is None:
        raise HTTPException(404, "alert not found")
    row.status = "ack"
    session.commit()
    return Envelope(data=_alert(row), meta=meta([row], scope))


@router.get("/recommendations", response_model=Envelope[list[RecommendationOut]])
def list_recommendations(
    session: SessionDep,
    scope: ScopeDep,
    kind: Annotated[Literal["buffer"] | None, Query()] = None,
) -> Envelope[list[RecommendationOut]]:
    q = select(Recommendation).where(scope.rows(Recommendation))
    if kind == "buffer":
        q = q.where(Recommendation.action_type == "increase_safety_stock")
    rows = session.scalars(q.limit(200)).all()
    return Envelope(data=[_rec(r) for r in rows], meta=meta(rows, scope))


@router.post("/recommendations/{rec_id}/decision", response_model=Envelope[RecommendationOut])
def decide(
    rec_id: UUID, body: DecisionIn, session: SessionDep, scope: ScopeDep
) -> Envelope[RecommendationOut]:
    """Accept or dismiss (NX-R04: nothing is auto-executed); the reason feeds K-04."""
    row = session.scalar(
        select(Recommendation).where(Recommendation.id == rec_id, scope.rows(Recommendation))
    )
    if row is None:
        raise HTTPException(404, "recommendation not found")
    row.status = body.decision
    row.feedback = body.feedback
    row.decided_at = datetime.now(UTC)
    session.commit()
    return Envelope(data=_rec(row), meta=meta([row], scope))


@router.post("/events/extract", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def extract_events(session: SessionDep) -> JobAccepted:
    """Queue C2 over the recent articles (then C1 refresh and buffer recommendations)."""
    return enqueue(session, "c2.process", {})
