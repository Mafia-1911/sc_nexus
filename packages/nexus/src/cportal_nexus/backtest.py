"""Backtest "time machine" (08 §6, NX-AC06): would Nexus have warned before Chattogram stalled?

Ground truth: disruption episodes in real GFW port calls at the gateway (daily departures at
≤ 50 % of the trailing 14-day median; nearby disrupted days merge). Alerts: GDACS/PortWatch
events the Nexus alert rule would have raised (LOCODE or ≤ 300 km, C2's thresholds on severity and
confidence), at the time each became available (point in time). An alert matches an episode that
starts 1 day before to 7 days after it. K-03 = hours from the alert to the episode's worst day;
K-04 = share of alerts that match an episode. Misses (episodes with no alert) are listed with
context labels (Eid, the 2024 unrest) that explain but never score. News history is not used:
GDELT coverage here starts in October 2026.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml
from cportal_core.models import DisruptionEvent, Port, PortCall
from cportal_core.paths import repo_root
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cportal_nexus import fusion


def config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((repo_root() / "config/priors/nexus.yaml").read_text())
    return dict(raw["backtest"])


@dataclass
class Episode:
    start: date
    end: date
    peak: date
    peak_ratio: float
    peak_departures: int
    normal: float
    context: list[str] = field(default_factory=list)


@dataclass
class AlertPoint:
    event_id: str
    title: str
    type: str
    at: datetime
    km: float | None
    level: str | None


def daily(departures: list[datetime], start: date, end: date) -> dict[date, int]:
    counts = Counter(d.date() for d in departures)
    return {start + timedelta(days=i): counts.get(start + timedelta(days=i), 0)
            for i in range((end - start).days + 1)}  # fmt: skip


def episodes(series: dict[date, int], cfg: dict[str, Any]) -> list[Episode]:
    days = sorted(series)
    hist = int(cfg["history_days"])
    flagged: list[tuple[date, float, int, float]] = []
    for i in range(hist, len(days)):
        normal = statistics.median(series[d] for d in days[i - hist : i])
        if normal < float(cfg["min_median"]):
            continue
        ratio = series[days[i]] / normal
        if ratio <= float(cfg["drop_ratio"]):
            flagged.append((days[i], ratio, series[days[i]], normal))
    out: list[Episode] = []
    gap = int(cfg["merge_gap_days"])
    for d, ratio, n, normal in flagged:
        last = out[-1] if out else None
        if last is not None and (d - last.end).days <= gap + 1:
            last.end = d
            if ratio < last.peak_ratio:
                last.peak, last.peak_ratio, last.peak_departures = d, round(ratio, 2), n
        else:
            out.append(Episode(d, d, d, round(ratio, 2), n, normal))
    return out


def label(ep: Episode, cfg: dict[str, Any]) -> list[str]:
    tags = []
    for c in cfg.get("context", []):
        day = date.fromisoformat(str(c["date"]))
        lo, hi = day - timedelta(days=int(c["before"])), day + timedelta(days=int(c["after"]))
        if ep.start <= hi and ep.end >= lo:
            tags.append(f"{c['label']} ({day.isoformat()})")
    return tags


def match(
    alerts: list[AlertPoint], eps: list[Episode], cfg: dict[str, Any]
) -> tuple[list[tuple[AlertPoint, Episode]], list[AlertPoint], list[Episode]]:
    before, after = int(cfg["match_before_days"]), int(cfg["match_after_days"])
    pairs: list[tuple[AlertPoint, Episode]] = []
    used: set[int] = set()
    for a in sorted(alerts, key=lambda x: x.at):
        day = a.at.date()
        lo, hi = day - timedelta(days=before), day + timedelta(days=after)
        cands = [(i, e) for i, e in enumerate(eps) if lo <= e.start <= hi]
        if cands:
            i, e = cands[0]
            pairs.append((a, e))
            used.add(i)
    matched = {id(a) for a, _ in pairs}
    false_alarms = [a for a in alerts if id(a) not in matched]
    missed = [e for i, e in enumerate(eps) if i not in used]
    return pairs, false_alarms, missed


def lead_hours(a: AlertPoint, e: Episode) -> float:
    peak = datetime.combine(e.peak, datetime.min.time(), UTC) + timedelta(hours=12)  # mid-day
    return round((peak - a.at).total_seconds() / 3600, 1)


def score(alerts: list[AlertPoint], eps: list[Episode], cfg: dict[str, Any]) -> dict[str, Any]:
    pairs, false_alarms, missed = match(alerts, eps, cfg)
    # K-03 is per disruption, from the *first* alert before it; precision counts alerts.
    first: dict[date, tuple[AlertPoint, Episode]] = {}
    for a, e in pairs:
        if e.start not in first or a.at < first[e.start][0].at:
            first[e.start] = (a, e)
    leads = [lead_hours(a, e) for a, e in first.values()]
    return {
        "k03_lead_time_h": {
            "median": statistics.median(leads) if leads else None,
            "min": min(leads) if leads else None,
            "max": max(leads) if leads else None,
            "n": len(leads),
        },
        "k04_precision": round(len(pairs) / len(alerts), 3) if alerts else None,
        "recall": round(len(first) / len(eps), 3) if eps else None,
        "episodes_warned": len(first),
        "alerts": len(alerts),
        "episodes": len(eps),
        "matched": [{"alert": a.title, "alert_at": a.at.isoformat(), "episode_start":
                     e.start.isoformat(), "peak": e.peak.isoformat(), "lead_h": lead_hours(a, e),
                     "peak_ratio": e.peak_ratio} for a, e in pairs],
        "false_alarms": [{"alert": a.title, "at": a.at.isoformat(), "type": a.type,
                          "km": a.km} for a in false_alarms],
        "missed": [{**{k: (v.isoformat() if isinstance(v, date) else v)
                       for k, v in asdict(e).items()}} for e in missed],
    }  # fmt: skip


# --- database ----------------------------------------------------------------------------------


def _departures(session: Session, locode: str, start: date) -> list[datetime]:
    rows = session.scalars(
        select(PortCall.departure_ts)
        .join(Port, Port.id == PortCall.port_id)
        .where(
            Port.locode == locode,
            PortCall.scenario_id.is_(None),
            PortCall.departure_ts.is_not(None),
            PortCall.departure_ts >= datetime.combine(start, datetime.min.time(), UTC),
        )
    ).all()
    return [d for d in rows if d is not None]


def _alerts(session: Session, cfg: dict[str, Any], start: date, end: date) -> list[AlertPoint]:
    rule = yaml.safe_load((repo_root() / "config/priors/disruptions.yaml").read_text())
    types, thresholds = rule["types"], rule["alert"]
    centre = func.ST_SetSRID(func.ST_MakePoint(cfg["centre"]["lon"], cfg["centre"]["lat"]), 4326)
    km = func.ST_Distance(func.geography(func.ST_Centroid(DisruptionEvent.geom)),
                          func.geography(centre)) / 1000.0  # fmt: skip
    seen = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
    rows = session.execute(
        select(DisruptionEvent, km, seen).where(
            DisruptionEvent.scenario_id.is_(None),
            DisruptionEvent.source_id.in_(fusion.config()["hazard_sources"]),
            seen >= datetime.combine(start, datetime.min.time(), UTC),
            seen <= datetime.combine(end, datetime.min.time(), UTC),
        )
    ).all()
    out: dict[str, AlertPoint] = {}
    for e, dist, at in sorted(rows, key=lambda r: r[2]):
        locode_hit = cfg["locode"] in (e.locodes or [])
        near = locode_hit or (dist is not None and dist <= float(cfg["alert_max_km"]))
        severity = float(e.severity or types.get(e.type, {}).get("severity", 0.5))
        conf = float(e.confidence or 0)
        if e.start_est is not None and (at - e.start_est).days > int(cfg["max_age_days"]):
            continue  # a feed republishing an old hazard (e.g. PortWatch backfill) is not an alert
        if not near or severity < thresholds["min_severity"] or conf < thresholds["min_confidence"]:
            continue
        key = (e.external_ids or {}).get("gdacs") or str(e.id)
        if key in out:
            continue  # the first feed to publish the hazard is the alert (point in time)
        km_ = None if dist is None else round(float(dist))
        out[key] = AlertPoint(str(e.id), e.title, e.type, at, km_, e.alert_level)
    return list(out.values())


def _hazards(session: Session, cfg: dict[str, Any], start: date) -> list[tuple[date, str, float]]:
    """Every hazard-feed event in Bangladesh (any distance), for labelling misses only."""
    centre = func.ST_SetSRID(func.ST_MakePoint(cfg["centre"]["lon"], cfg["centre"]["lat"]), 4326)
    km = (
        func.ST_Distance(
            func.geography(func.ST_Centroid(DisruptionEvent.geom)), func.geography(centre)
        )
        / 1000.0
    )
    rows = session.execute(
        select(DisruptionEvent.start_est, DisruptionEvent.title, km).where(
            DisruptionEvent.scenario_id.is_(None),
            DisruptionEvent.source_id.in_(fusion.config()["hazard_sources"]),
            DisruptionEvent.start_est >= datetime.combine(start, datetime.min.time(), UTC),
            DisruptionEvent.country_iso3.contains(["BGD"]),
        )
    ).all()
    return [(s.date(), t, round(float(k or 0))) for s, t, k in rows if s is not None]


def run(session: Session) -> dict[str, Any]:
    cfg = config()
    start = date.fromisoformat(str(cfg["start"]))
    deps = _departures(session, cfg["locode"], start)
    if not deps:
        return {"error": "no port calls"}
    end = max(d.date() for d in deps) - timedelta(days=1)  # the last day may be partial
    series = daily(deps, start, end)
    eps = episodes(series, cfg)
    hazards = _hazards(session, cfg, start)
    window_d = int(cfg["context_hazard_days"])
    for e in eps:
        e.context = label(e, cfg)
        e.context += sorted({f"{t} at {k} km" for d, t, k in hazards
                             if e.start - timedelta(days=window_d) <= d <= e.start})  # fmt: skip
    alerts = _alerts(session, cfg, start + timedelta(days=int(cfg["history_days"])), end)
    report = score(alerts, eps, cfg)
    days = len(series)
    report["window"] = {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                        "departures": len(deps),
                        "mean_daily": round(len(deps) / days, 1) if days else None}  # fmt: skip
    report["missed_explained"] = sum(1 for m in report["missed"] if m["context"])
    report["config"] = {k: v for k, v in cfg.items() if k != "context"}
    report["note"] = (
        "ground truth = port-data episodes; alerts = hazard feeds only (no news history)"
    )
    report["mean_lead_days"] = (
        None
        if report["k03_lead_time_h"]["median"] is None
        else round(report["k03_lead_time_h"]["median"] / 24, 1)
    )
    return report
