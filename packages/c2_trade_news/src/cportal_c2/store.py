"""Database side of C2: read the article window, write events, mentions, links and alerts.

Outputs derived from real articles are real rows (`data_mode` live or replay, `source_id`
"c2"). Links from a real event to a scenario's fictional facilities are synthetic rows of that
scenario: "in scenario X, this real flood touches these fictional plants".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid5

from cportal_core.models import (
    Alert,
    Article,
    DisruptionEvent,
    EventEntityLink,
    EventMention,
    Facility,
    Scenario,
)
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cportal_c2 import RULES_VERSION
from cportal_c2.cluster import NS, Event, Mention
from cportal_c2.config import Config
from cportal_c2.extract import Extraction, extract
from cportal_c2.llm import apply, verdicts

SOURCE = "c2"


def outlet(source_name: str | None, url: str) -> str:
    return (source_name or urlparse(url).netloc or url).lower().removeprefix("www.")


def read_mentions(
    session: Session, since: datetime, cfg: Config, scenario_id: UUID | None = None
) -> list[Mention]:
    """Real articles (no scenario), or one scenario's synthetic articles."""
    scope = (
        Article.is_synthetic.is_(False)
        if scenario_id is None
        else Article.scenario_id == scenario_id
    )
    rows = session.execute(
        select(
            Article.id,
            Article.source_id,
            Article.source_name,
            Article.url,
            Article.title,
            Article.snippet,
            Article.published_at,
            Article.data_mode,
        ).where(scope, Article.published_at >= since)
    ).all()
    llm = verdicts(session, [r.id for r in rows])
    out = []
    for r in rows:
        x = extract(str(r.id), r.title, r.snippet, r.published_at, cfg)
        if str(r.id) in llm:
            x = apply(x, llm[str(r.id)])
        if not x.is_supply_chain_disruption:
            continue
        out.append(
            Mention(
                extraction=x,
                source_id=r.source_id,
                outlet=outlet(r.source_name, r.url),
                published=r.published_at,
                url=r.url,
                title=x.text.split(". ")[0][:300],
                data_mode=r.data_mode,
            )
        )
    return out


def _lineage(data_mode: str, key: str, scenario_id: UUID | None = None) -> dict[str, Any]:
    synthetic = scenario_id is not None
    return {
        "source_id": SOURCE,
        "source_record_id": key[:256],
        "data_mode": "synthetic" if synthetic else data_mode,
        "is_synthetic": synthetic,
        "scenario_id": scenario_id,
        "generator_version": RULES_VERSION,
    }


def evidence(x: Extraction) -> dict[str, list[Any]]:
    """field → [start, end, quote], the grounding the UI highlights."""
    spans: dict[str, list[Any]] = {}
    for name, span in (("event_type", x.type_span), ("start", x.start_span),
                       ("duration", x.duration_span), ("status", x.status_span)):  # fmt: skip
        if span is not None:
            spans[name] = [span.start, span.end, span.text]
    for i, loc in enumerate(x.locations):
        spans[f"location_{i}"] = [loc.span.start, loc.span.end, loc.span.text]
    for g in x.magnitude:
        spans[f"magnitude_{g.metric}"] = [g.span.start, g.span.end, g.span.text]
    return spans


def write(
    session: Session,
    events: list[Event],
    since: datetime,
    cfg: Config,
    scenario_id: UUID | None = None,
) -> dict[str, int]:
    """Replace C2's events in the window (and scope) with these; alerts keep status by key."""
    keep = {e.id for e in events}
    in_scope = (
        DisruptionEvent.scenario_id.is_(None)
        if scenario_id is None
        else DisruptionEvent.scenario_id == scenario_id
    )
    stale = session.scalars(
        select(DisruptionEvent.id).where(
            DisruptionEvent.source_id == SOURCE, DisruptionEvent.first_seen >= since, in_scope
        )
    ).all()
    gone = [i for i in stale if i not in keep]
    if gone:
        session.execute(delete(Alert).where(Alert.event_id.in_(gone)))
        session.execute(delete(DisruptionEvent).where(DisruptionEvent.id.in_(gone)))
    links = mentions = alerts = 0
    # A real event can touch every scenario's plants; a scenario's event only its own.
    scenarios = [
        (sid, key)
        for sid, key in session.execute(select(Scenario.id, Scenario.key)).all()
        if scenario_id is None or sid == scenario_id
    ]
    area_types = set(cfg.priors["area_types"])
    for e in events:
        prior = cfg.prior(e.type)
        session.merge(
            DisruptionEvent(
                id=e.id,
                **_lineage(e.data_mode, str(e.id), scenario_id),
                available_at=e.first_seen,
                type=e.type,
                title=e.title,
                summary=e.summary,
                status=e.status,
                severity=e.severity,
                confidence=e.confidence,
                start_est=e.start,
                start_uncertainty_h=e.start_uncertainty_h,
                end_est=(e.start + timedelta(hours=e.duration_p50_h)) if e.start else None,
                duration_p50_h=e.duration_p50_h,
                duration_p90_h=e.duration_p90_h,
                geom=from_shape(Point(e.lon, e.lat), srid=4326),
                locodes=e.locodes,
                country_iso3=e.countries,
                first_seen=e.first_seen,
                last_updated=e.last_updated,
            )
        )
        for m in e.mentions:
            x = m.extraction
            session.merge(
                EventMention(
                    id=uuid5(NS, f"mention:{x.article_id}:{RULES_VERSION}"),
                    **_lineage(m.data_mode, x.article_id, scenario_id),
                    available_at=m.published,
                    event_id=e.id,
                    article_id=UUID(x.article_id),
                    extracted=x.model_dump(mode="json"),
                    evidence_spans=evidence(x),
                    extractor_version=x.extractor if x.extractor != "rules" else RULES_VERSION,
                    extraction_confidence=x.confidence,
                )
            )
            mentions += 1
        if e.type in area_types and e.clusters:
            for scenario_id, _key in scenarios:
                for fid in session.scalars(
                    select(Facility.id).where(
                        Facility.scenario_id == scenario_id, Facility.cluster.in_(e.clusters)
                    )
                ):
                    session.merge(
                        EventEntityLink(
                            id=uuid5(NS, f"link:{e.id}:{scenario_id}:{fid}"),
                            source_id=SOURCE,
                            source_record_id=str(e.id),
                            data_mode="synthetic",
                            is_synthetic=True,
                            scenario_id=scenario_id,
                            generator_version=RULES_VERSION,
                            event_id=e.id,
                            entity_type="facility",
                            entity_id=fid,
                            link_method="geo_buffer",
                            link_confidence=round(e.confidence * 0.6, 3),
                            impact_hint={
                                "capacity_pct": prior["capacity_pct"],
                                "duration_d": round(e.duration_p50_h / 24, 1),
                                "cluster": True,
                            },
                        )
                    )
                    links += 1
        alerts += _alert(session, e, cfg, scenario_id)
    return {
        "events": len(events),
        "mentions": mentions,
        "links": links,
        "alerts": alerts,
        "removed": len(gone),
    }


def _alert(session: Session, e: Event, cfg: Config, scenario_id: UUID | None = None) -> int:
    rule = cfg.priors["alert"]
    if (
        e.status == "resolved"
        or e.severity < rule["min_severity"]
        or e.confidence < rule["min_confidence"]
    ):
        return 0
    key = f"c2:{e.id}"
    existing = session.scalar(select(Alert).where(Alert.dedupe_key == key))
    label = "critical" if e.severity >= 0.8 else "high" if e.severity >= 0.65 else "medium"
    refs = [{"type": "port", "locode": c} for c in e.locodes] + [
        {"type": "cluster", "id": c} for c in e.clusters
    ]
    body = (
        f"{e.type.replace('_', ' ').lower()} · severity {e.severity:.2f} · confidence "
        f"{e.confidence:.2f} · {len(e.outlets)} outlet(s): {', '.join(e.outlets[:4])}"
    )
    if existing is None:
        session.add(
            Alert(
                id=uuid5(NS, key),
                **_lineage(e.data_mode, key, scenario_id),
                kind="disruption",
                severity=label,
                title=e.title,
                body=body,
                entity_refs=refs,
                event_id=e.id,
                status="open",
                dedupe_key=key,
            )
        )
    else:  # keep ack / snooze status; refresh the content
        existing.severity, existing.title, existing.body, existing.entity_refs = (
            label,
            e.title,
            body,
            refs,
        )
    return 1


def window_start(now: datetime | None = None, days: int = 14) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=days)
