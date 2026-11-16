"""/brief: today's brief for the Control Tower (08 §5, NX-R05), from structured rows only.

A deterministic template (Q-17 / U-09: no LLM copilot): every sentence is built from rows the
other endpoints serve, and every sentence with a number cites the rows it rests on (events,
alerts, recommendations, a CPA poll, a gate day, the C4 split, a scenario result). Port numbers
come from the KPI functions themselves, so the brief and the KPI strip always agree. One data
source per view (A-111): real data or the selected scenario, never both.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from cportal_core.models import (
    Alert,
    DisruptionEvent,
    GateFlowDaily,
    PortStateSnapshot,
    Recommendation,
    Scenario,
    ScenarioResult,
)
from fastapi import APIRouter
from sqlalchemy import func, select

from cportal_api.deps import DHAKA, ScopeDep, SessionDep, meta
from cportal_api.routers import events as ev
from cportal_api.routers import kpis as kp
from cportal_api.routers import port_live
from cportal_api.schemas import BriefCite, BriefLine, BriefOut, Envelope, Kpi
from cportal_api.waits import berth_waits

router = APIRouter(tags=["nexus"])

ACTION = {
    "increase_safety_stock": "Raise safety stock",
    "pull_forward_po": "Pull the purchase order forward",
    "reroute": "Export via Mongla",
    "rework": "Rework the lot",
    "replace_production": "Replace production",
    "expedite_air": "Air-freight the order",
    "notify_customer": "Notify the buyer",
}
SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}  # alerts (words)
Tone = Literal["info", "watch", "risk"]


def _level(sev: float | None) -> str:
    """Event severity is 0–1 (C2 / feeds); say it in words."""
    if sev is None:
        return "unrated"
    return "high" if sev >= 0.8 else "medium" if sev >= 0.5 else "low"


def _t(ts: datetime) -> str:
    return f"{ts.astimezone(DHAKA):%d %b, %H:%M}"


def _n(v: float | int | None, digits: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{digits}f}" if digits else f"{round(v):,}"


def _kind(t: str) -> str:
    return t.replace("_", " ").lower()


def _snapshot_cite(snap: PortStateSnapshot | None, href: str = "/ports") -> list[BriefCite]:
    if snap is None:
        return []
    return [BriefCite(kind="snapshot", id=str(snap.id), label=f"CPA poll {_t(snap.ts)}", href=href)]


def _kpi_cite(k: Kpi, snap: PortStateSnapshot | None) -> list[BriefCite]:
    if snap is not None and "DS-PORT-10" in k.meta.sources:
        return _snapshot_cite(snap)
    src = ", ".join(k.meta.sources) or "source"
    return [
        BriefCite(kind="source", id=src, label=f"{src} as of {_t(k.meta.as_of)}", href="/ports")
    ]


# --- real data ------------------------------------------------------------------------------------


def _latest_cpa(session: SessionDep) -> PortStateSnapshot | None:
    return session.scalar(
        select(PortStateSnapshot)
        .where(PortStateSnapshot.source_id == "DS-PORT-10")
        .order_by(PortStateSnapshot.ts.desc())
        .limit(1)
    )


def _port_lines(session: SessionDep, scope: ScopeDep, ks: dict[str, Kpi]) -> list[BriefLine]:
    snap = _latest_cpa(session)
    out: list[BriefLine] = []
    anch, wait = ks.get("vessels_at_anchorage"), ks.get("mean_wait_24h")
    if anch is not None and anch.value is not None:
        extra = f" ({anch.detail})" if anch.detail else ""
        out.append(BriefLine(
            text=f"{anch.label}: {_n(anch.value)}{extra}.", cites=_kpi_cite(anch, snap),
        ))  # fmt: skip
    if wait is not None and wait.value is not None:
        cites = _kpi_cite(wait, snap)
        split = berth_waits(session) if "real berthings" in (wait.detail or "") else None
        if split is not None:
            cites = [BriefCite(
                kind="model", id="c4.berth_split",
                label=f"C4 wait split: {split['n']} berthings to {split['to']:%d %b}",
                href="/ports",
            )]  # fmt: skip
        tone: Tone = "watch" if split and split["over_24h_pct"] >= 20 else "info"
        out.append(BriefLine(
            text=f"{wait.label}: {_n(wait.value, 1)} {wait.unit}"
            + (f" ({wait.detail})." if wait.detail else "."),
            tone=tone, cites=cites,
        ))  # fmt: skip
    fresh = snap is not None and datetime.now(UTC) - snap.ts <= port_live.FRESH
    if scope.horizon != "now" or not fresh:
        return out
    # Yards: the fullest terminal yards from the latest poll that read them.
    yard = session.execute(
        select(PortStateSnapshot.id, PortStateSnapshot.ts, PortStateSnapshot.yard["yards"])
        .where(
            PortStateSnapshot.source_id == "DS-PORT-10",
            PortStateSnapshot.yard["yards"].astext != "null",
        )
        .order_by(PortStateSnapshot.ts.desc())
        .limit(1)
    ).first()
    if yard is not None and yard[2]:
        rows = [y for y in yard[2] if y.get("capacity_teu")]
        cap = sum(y["capacity_teu"] for y in rows)
        used = sum(y.get("used_teu") or 0 for y in rows)
        full = sorted(rows, key=lambda y: -(y.get("used_pct") or 0))[:2]
        if cap and full:
            parts = ", ".join(f"{y['yard']} {_n(y.get('used_pct'))}%" for y in full)
            out.append(BriefLine(
                text=f"Container yards are at {_n(100 * used / cap)}% of capacity overall; "
                f"the fullest: {parts}.",
                tone="watch" if used > cap else "info",
                cites=[BriefCite(kind="snapshot", id=str(yard[0]),
                                 label=f"CPA yard report {_t(yard[1])}", href="/ports")],
            ))  # fmt: skip
    # Arrivals: due in the next 24 h, and those past their declared ETA (agents' declarations).
    live = port_live.port_live(session).data
    now = datetime.now(UTC)
    etas = [datetime.fromisoformat(x["eta"]) for x in live.get("expected", []) if x.get("eta")]
    due = sum(1 for t in etas if now <= t <= now + timedelta(hours=24))
    overdue = sum(1 for t in etas if t < now)
    if etas:
        out.append(BriefLine(
            text=f"{_n(due)} ships are due in the next 24 h, and {_n(overdue)} are past the "
            "arrival time their agents declared without having arrived.",
            cites=_snapshot_cite(snap),
        ))  # fmt: skip
    # Gates: the last full Dhaka day against the mean of the days before it.
    today = now.astimezone(DHAKA).date()
    days = session.execute(
        select(GateFlowDaily.date, func.sum(GateFlowDaily.in_box), func.sum(GateFlowDaily.out_box))
        .where(GateFlowDaily.date < today, GateFlowDaily.date >= today - timedelta(days=31))
        .group_by(GateFlowDaily.date)
        .order_by(GateFlowDaily.date.desc())
    ).all()
    if days:
        d, i, o = days[0]
        prev = days[1:]
        mean = (
            f" (mean of the {len(prev)} days before: {_n(sum(r[1] for r in prev) / len(prev))} in,"
            f" {_n(sum(r[2] for r in prev) / len(prev))} out)"
            if prev
            else ""
        )
        out.append(BriefLine(
            text=f"Port gates on {d:%d %b}: {_n(i)} containers in, {_n(o)} out{mean}.",
            cites=[BriefCite(kind="gates", id=d.isoformat(), label=f"CPA gates {d:%d %b}",
                             href="/ports")],
        ))  # fmt: skip
    return out


def _event_lines(
    session: SessionDep, scope: ScopeDep, alerted: set[UUID] | None = None
) -> list[BriefLine]:
    """Active disruptions; those already raised as alerts above are counted, not repeated."""
    rows = kp.active_events(session, scope)
    if not rows:
        return [BriefLine(text="No active disruption touches Bangladesh's ports or corridor.",
                          cites=[])]  # fmt: skip
    fused = ev._fusion(session, scope, [e.id for e in rows])

    def conf(e: DisruptionEvent) -> float:
        p = fused.get(e.id)
        return float(p.value) if p is not None and p.value is not None else (e.confidence or 0.0)

    top = sorted(rows, key=lambda e: (-(e.severity or 0.0), -conf(e)))[:3]
    out = [BriefLine(
        text=f"{_n(len(rows))} active disruption{'s' if len(rows) != 1 else ''} in Bangladesh; "
        "the most serious below.",
        tone="watch", cites=[BriefCite(kind="event", id=str(e.id), label=e.title[:60],
                                       href="/radar") for e in top],
    )]  # fmt: skip
    for e in top:
        if alerted and e.id in alerted:
            continue
        p = fused.get(e.id)
        how = "fused confidence" if p is not None else "confidence"
        out.append(BriefLine(
            text=f"{e.title} ({_kind(e.type)}, {_level(e.severity)} severity): {how} "
            f"{_n(100 * conf(e))}%.",
            tone="risk" if (e.severity or 0) >= 0.8 else "watch",
            cites=[BriefCite(kind="event", id=str(e.id), label=f"{e.source_id} event",
                             href="/radar")],
        ))  # fmt: skip
    return out


# --- a scenario -----------------------------------------------------------------------------------


def _top_alerts(session: SessionDep, scope: ScopeDep) -> list[Alert]:
    alerts = session.scalars(select(Alert).where(scope.rows(Alert), Alert.status == "open")).all()
    return sorted(alerts, key=lambda a: (SEVERITY.get(a.severity, 5), a.created_at))[:3]


def _scenario_lines(session: SessionDep, scope: ScopeDep, ks: dict[str, Kpi]) -> list[BriefLine]:
    sid = scope.scenario_id
    out: list[BriefLine] = []
    for a in _top_alerts(session, scope):
        out.append(BriefLine(
            text=f"Alert ({a.severity}): {a.title}.", tone="risk" if a.severity in
            ("critical", "high") else "watch",
            cites=[BriefCite(kind="alert", id=str(a.id), label=f"alert {str(a.id)[:8]}",
                             href="/radar")],
        ))  # fmt: skip
    # Orders at risk: the KPI strip's own number (K-05), so the brief and the strip agree.
    risk = ks.get("orders_at_risk")
    if risk is not None and risk.value is not None:
        detail = f" ({risk.detail})" if risk.detail else ""
        out.append(BriefLine(
            text=f"{risk.label}: {_n(risk.value)}{detail}.",
            tone="risk" if risk.value else "info",
            cites=[BriefCite(kind="scenario", id=str(sid), label="orders at risk (K-05)",
                             href="/")],
        ))  # fmt: skip
    recs = [ev._rec(r) for r in session.scalars(
        select(Recommendation).where(
            scope.rows(Recommendation), Recommendation.status == "proposed"
        )
    )]  # fmt: skip
    for r in sorted(recs, key=ev._by_value)[:2]:
        if r.expected_value_usd is None:
            continue
        conf = f", confidence {_n(100 * r.confidence)}%" if r.confidence is not None else ""
        out.append(BriefLine(
            text=f"Recommended: {ACTION.get(r.action_type, _kind(r.action_type))}, expected "
            f"value US${_n(r.expected_value_usd)}{conf}.",
            cites=[BriefCite(kind="recommendation", id=str(r.id),
                             label=f"recommendation {str(r.id)[:8]}", href="/radar")],
        ))  # fmt: skip
    anch, wait = ks.get("vessels_at_anchorage"), ks.get("mean_wait_24h")
    cite = [BriefCite(kind="scenario", id=str(sid), label="simulated port", href="/ports")]
    if anch is not None and anch.value is not None:
        w = (
            f"; {wait.label.lower()}: {_n(wait.value, 1)} {wait.unit}"
            if wait and wait.value
            else ""
        )
        out.append(BriefLine(
            text=f"Simulated port: {_n(anch.value)} vessels at the anchorage{w}.", cites=cite,
        ))  # fmt: skip
    res = session.scalar(
        select(ScenarioResult).where(
            ScenarioResult.run_scenario_id == sid, ScenarioResult.capability == "c4"
        )
    )
    k: dict[str, Any] = (res.kpis or {}) if res is not None else {}
    p, b = k.get("scenario") or {}, k.get("without_disruption") or {}
    if p.get("p90_wait_h") is not None:
        without = f" ({_n(b.get('p90_wait_h'), 1)} h without the shock)" if b else ""
        out.append(BriefLine(
            text=f"Next 14 days: P90 berth wait {_n(p['p90_wait_h'], 1)} h{without}, peak "
            f"{_n(p.get('peak_waiting_for_berth'))} ships waiting.",
            tone="watch" if b and p["p90_wait_h"] > (b.get("p90_wait_h") or 0) else "info",
            cites=[BriefCite(kind="scenario", id=str(res.id), label="port projection (DES)",  # type: ignore[union-attr]
                             href="/ports")],
        ))  # fmt: skip
    return out


@router.get("/brief", response_model=Envelope[BriefOut])
def brief(session: SessionDep, scope: ScopeDep) -> Envelope[BriefOut]:
    """Today's brief: port state, disruptions, and (in a scenario) at-risk shipments and the best
    recommendations, each sentence with the rows it cites."""
    ks = {k.key: k for k in kp.kpis(session, scope).data.kpis}
    if scope.scenario_id is None:
        lines = _port_lines(session, scope, ks) + _event_lines(session, scope)
        when = scope.as_of or datetime.now(UTC)
        title = f"Brief · Chattogram · {when.astimezone(DHAKA):%a %d %b %Y}"
    else:
        name = session.scalar(select(Scenario.name).where(Scenario.id == scope.scenario_id))
        alerted = {a.event_id for a in _top_alerts(session, scope) if a.event_id is not None}
        lines = _scenario_lines(session, scope, ks) + _event_lines(session, scope, alerted)
        when = datetime.now(UTC)
        title = f"Scenario brief · {name or scope.key}"
    return Envelope(
        data=BriefOut(title=title, as_of=when, lines=lines),
        meta=meta([], scope, as_of=when, note="template over structured rows; every number cited"),
    )
