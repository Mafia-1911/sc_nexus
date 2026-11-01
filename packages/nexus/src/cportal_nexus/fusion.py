"""Evidence fusion (08 §3, NX-R03, NX-AC03): one explainable confidence per disruption event.

    logit(conf) = logit(base) + prior(type) + Σ weight[kind] · strength

base = C2's news confidence (or the hazard feed's reliability for a hazard event). Signals are
corroboration of other kinds, as of `now` (only facts with `available_at` ≤ now):
- hazard: a GDACS/PortWatch event of a related type, near in space and time (one per GDACS id);
- news: news events that a hazard event explains (for the hazard event itself);
- physical: departures at the event's LOCODE down ≥ 50 % in the last 24 h vs the 14-day mean.
Absence of a physical anomaly is recorded as a check, never held against the event. An event
backed only by one low-reliability outlet stays ≤ 0.5 (NX-R03). Weights: `fusion.yaml` (A-093).
Output: one `prediction` row per event and scope (nexus, `event_confidence`).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml
from cportal_core.models import (
    Article,
    DisruptionEvent,
    EventMention,
    Port,
    PortCall,
    Prediction,
)
from cportal_core.paths import repo_root
from sqlalchemy import and_, delete, func, insert, or_, select
from sqlalchemy.orm import Session

from cportal_nexus import FUSION_VERSION

NS = uuid5(NAMESPACE_URL, "cportal/nexus/fusion")
TARGET = "event_confidence"
STRONG = ("hazard", "physical", "official")


@cache
def config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((repo_root() / "config/priors/fusion.yaml").read_text())
    return raw


@dataclass(frozen=True)
class Ev:
    id: UUID
    type: str
    source_id: str
    title: str
    confidence: float
    alert_level: str | None
    start: datetime | None
    lat: float | None
    lon: float | None
    locodes: tuple[str, ...] = ()
    gdacs: str | None = None
    outlets: int = 0
    url: str | None = None


@dataclass
class Signal:
    kind: str  # news | hazard | physical | official
    label: str
    source_id: str
    strength: float
    ref_type: str  # event | port_calls
    ref_id: str | None = None
    observed_at: datetime | None = None
    url: str | None = None
    contribution: float = 0.0


@dataclass
class Fused:
    event_id: UUID
    base: float
    confidence: float
    signals: list[Signal] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    capped: bool = False


def logit(p: float) -> float:
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def km(a: Ev, b: Ev) -> float:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return math.inf
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))  # type: ignore[arg-type]
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def is_hazard(e: Ev) -> bool:
    return e.source_id in config()["hazard_sources"]


def near(a: Ev, b: Ev) -> bool:
    m = config()["match"]
    place = bool(set(a.locodes) & set(b.locodes)) or km(a, b) <= float(m["max_km"])
    if a.start is None or b.start is None:
        return place
    return place and abs((a.start - b.start).total_seconds()) <= float(m["max_hours"]) * 3600


def explains(hazard: Ev, other: Ev) -> bool:
    return other.type in config()["match"]["related"].get(hazard.type, [hazard.type])


def corroborate(events: list[Ev]) -> dict[UUID, list[Signal]]:
    """Cross-event signals: hazards corroborate news they explain, and news corroborates hazards."""
    cfg = config()
    out: dict[UUID, list[Signal]] = {e.id: [] for e in events}
    for e in events:
        hazards: dict[str, Signal] = {}
        for o in events:
            if o.id == e.id or not near(e, o):
                continue
            if is_hazard(o) and not is_hazard(e) and explains(o, e):
                s = float(cfg["hazard_alert_strength"].get(o.alert_level or "default", 0.5))
                key = o.gdacs or str(o.id)
                if key not in hazards or s > hazards[key].strength:
                    hazards[key] = Signal(
                        "hazard", f"{o.title} ({o.alert_level or 'alert'})", o.source_id, s,
                        "event", str(o.id), o.start, o.url,
                    )  # fmt: skip
            elif is_hazard(e) and not is_hazard(o) and explains(e, o) and o.confidence > 0:
                out[e.id].append(
                    Signal("news", o.title, o.source_id, round(o.confidence, 3), "event",
                           str(o.id), o.start, o.url)
                )  # fmt: skip
        out[e.id].extend(hazards.values())
    return out


def fuse(e: Ev, signals: list[Signal], checks: list[dict[str, Any]] | None = None) -> Fused:
    cfg = config()
    base = e.confidence if e.confidence > 0 else 0.5
    x = logit(base) + float(cfg["prior_logit"].get(e.type, cfg["prior_logit"]["default"]))
    for s in signals:
        s.contribution = round(float(cfg["weights"][s.kind]) * s.strength, 3)
        x += s.contribution
    conf = sigmoid(x)
    reliability = float(_reliability().get(e.source_id, _reliability().get("default", 0.5)))
    lonely = (
        not is_hazard(e)
        and not any(s.kind in STRONG for s in signals)
        and e.outlets + sum(1 for s in signals if s.kind == "news") <= 1
        and reliability <= float(cfg["low_reliability_max"])
    )
    capped = lonely and conf > float(cfg["single_source_cap"])
    if capped:
        conf = float(cfg["single_source_cap"])
    return Fused(e.id, round(base, 3), round(conf, 3), signals, checks or [], capped)


@cache
def _reliability() -> dict[str, float]:
    raw = yaml.safe_load((repo_root() / "config/priors/disruptions.yaml").read_text())
    return {k: float(v) for k, v in raw["source_reliability"].items()}


# --- database ----------------------------------------------------------------------------------


def _events(session: Session, scenario_id: UUID | None, now: datetime) -> list[Ev]:
    seen = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
    scope = (
        DisruptionEvent.scenario_id.is_(None)
        if scenario_id is None
        else or_(DisruptionEvent.scenario_id == scenario_id, DisruptionEvent.scenario_id.is_(None))
    )
    outlets = (
        select(func.count(func.distinct(Article.source_name)))
        .join(EventMention, EventMention.article_id == Article.id)
        .where(EventMention.event_id == DisruptionEvent.id)
        .scalar_subquery()
    )
    url = (
        select(Article.url)
        .join(EventMention, EventMention.article_id == Article.id)
        .where(EventMention.event_id == DisruptionEvent.id)
        .order_by(Article.published_at)
        .limit(1)
        .scalar_subquery()
    )
    centroid = func.ST_Centroid(DisruptionEvent.geom)
    rows = session.execute(
        select(DisruptionEvent, func.ST_Y(centroid), func.ST_X(centroid), outlets, url).where(
            scope,
            or_(seen.is_(None), seen <= now),
            DisruptionEvent.status.notin_(("resolved", "retracted")),
        )
    ).all()
    return [
        Ev(e.id, e.type, e.source_id, e.title, float(e.confidence or 0), e.alert_level,
           e.start_est, lat, lon, tuple(e.locodes or ()), (e.external_ids or {}).get("gdacs"),
           int(n or 0), e.url or u)
        for e, lat, lon, n, u in rows
    ]  # fmt: skip


def _physical(
    session: Session, e: Ev, scenario_id: UUID | None, now: datetime
) -> tuple[list[Signal], list[dict[str, Any]]]:
    p = config()["physical"]
    if e.type not in p["types"] or not e.locodes or e.start is None or e.start > now:
        return [], []
    window = timedelta(hours=float(p["window_h"]))
    since = now - window - timedelta(days=int(p["history_days"]))
    scope = (
        PortCall.scenario_id.is_(None)
        if scenario_id is None
        else PortCall.scenario_id == scenario_id
    )
    signals, checks = [], []
    for code in e.locodes:
        recent, hist = session.execute(
            select(
                func.count().filter(PortCall.departure_ts > now - window),
                func.count().filter(PortCall.departure_ts <= now - window),
            )
            .join(Port, Port.id == PortCall.port_id)
            .where(
                Port.locode == code, scope,
                PortCall.departure_ts > since, PortCall.departure_ts <= now,
                or_(PortCall.available_at.is_(None), PortCall.available_at <= now),
            )
        ).one()  # fmt: skip
        daily = hist / int(p["history_days"])
        if daily < float(p["min_daily_departures"]):
            checks.append(
                {"kind": "physical", "locode": code, "label": "too few port calls to judge"}
            )
            continue
        expected = daily * window.total_seconds() / 86400
        drop = max(0.0, 1 - recent / expected)
        label = f"Departures from {code}: {recent} in {p['window_h']} h vs {expected:.1f} expected"
        if drop >= float(p["departures_drop_min"]):
            signals.append(Signal("physical", label, "c4", round(min(drop, 1.0), 3), "port_calls",
                                  code, now))  # fmt: skip
        else:
            checks.append(
                {"kind": "physical", "locode": code, "label": label + " (no anomaly yet)"}
            )
    return signals, checks


def refresh(
    session: Session, scenario_id: UUID | None, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    events = _events(session, scenario_id, now)
    cross = corroborate(events)
    results = []
    for e in events:
        phys, checks = _physical(session, e, scenario_id, now)
        results.append(fuse(e, cross[e.id] + phys, checks))
    session.execute(
        delete(Prediction).where(
            Prediction.capability == "nexus",
            Prediction.target_type == TARGET,
            Prediction.scenario_id.is_(None) if scenario_id is None
            else Prediction.scenario_id == scenario_id,
        )
    )  # fmt: skip
    lineage = {
        "source_id": "nexus",
        "data_mode": "live" if scenario_id is None else "synthetic",
        "is_synthetic": scenario_id is not None,
        "scenario_id": scenario_id,
        "generator_version": FUSION_VERSION,
    }
    rows = [
        {
            "id": uuid5(NS, f"{scenario_id}:{f.event_id}"), **lineage,
            "source_record_id": f"{TARGET}:{f.event_id}", "available_at": now,
            "capability": "nexus", "target_type": TARGET, "target_id": f.event_id,
            "as_of": now, "horizon_h": None, "value": f.confidence, "quantiles": {},
            "dist_params": {"base": f.base, "capped": f.capped},
            "model_version_id": None,
            "explanation": {
                "signals": [{**asdict(s), "observed_at": s.observed_at.isoformat()
                             if s.observed_at else None} for s in f.signals],
                "checks": f.checks,
                "rule": "logit(conf) = logit(base) + Σ weight·strength (fusion.yaml)",
            },
            "features_hash": None,
        }
        for f in results
    ]  # fmt: skip
    if rows:
        session.execute(insert(Prediction), rows)
    corroborated = sum(1 for f in results if {s.kind for s in f.signals} - {"news"})
    return {"events": len(results), "corroborated": corroborated}


def fused_confidence(session: Session, scenario_id: UUID | None) -> dict[UUID, float]:
    rows = session.execute(
        select(Prediction.target_id, Prediction.value).where(
            Prediction.capability == "nexus",
            Prediction.target_type == TARGET,
            and_(
                Prediction.scenario_id.is_(None)
                if scenario_id is None
                else Prediction.scenario_id == scenario_id
            ),
        )
    ).all()
    return {t: float(v) for t, v in rows if v is not None}
