"""Nexus alerts for hazard-feed events (08 §3–§4): C2 alerts on news; this alerts on forecasts.

A GDACS/PortWatch event raises a `disruption` alert in a scope when, as of that scope's `now`,
it is known (`available_at`), not resolved, touches the network (a LOCODE) and passes C2's alert
thresholds on severity (the event's, or its type prior) and the *fused* confidence. One alert
per GDACS id (both feeds carry the same storm). The recommendation engine then runs on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml
from cportal_core.models import Alert, DisruptionEvent
from cportal_core.paths import repo_root
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cportal_nexus import FUSION_VERSION, fusion

NS = uuid5(NAMESPACE_URL, "cportal/nexus/alerts")


def _priors() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(
        (repo_root() / "config/priors/disruptions.yaml").read_text()
    )
    return raw


def refresh(session: Session, scenario_id: UUID | None, now: datetime) -> int:
    pri = _priors()
    rule, types = pri["alert"], pri["types"]
    fused = fusion.fused_confidence(session, scenario_id)
    seen = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
    scope = (  # one data source per view (A-111): a scenario sees only its own events
        DisruptionEvent.scenario_id.is_(None)
        if scenario_id is None
        else DisruptionEvent.scenario_id == scenario_id
    )
    events = session.scalars(
        select(DisruptionEvent)
        .where(
            scope,
            DisruptionEvent.source_id.in_(fusion.config()["hazard_sources"]),
            DisruptionEvent.status.notin_(("resolved", "retracted")),
            DisruptionEvent.locodes != [],
            seen <= now,
        )
        .order_by(seen)
    ).all()
    session.execute(
        delete(Alert).where(
            Alert.source_id == "nexus",
            Alert.status == "open",
            Alert.scenario_id.is_(None)
            if scenario_id is None
            else Alert.scenario_id == scenario_id,
        )
    )
    raised, storms = 0, set()
    for e in events:
        storm = (e.external_ids or {}).get("gdacs") or str(e.id)
        severity = float(e.severity or types.get(e.type, {}).get("severity", 0.5))
        conf = fused.get(e.id, float(e.confidence or 0))
        if storm in storms or severity < rule["min_severity"] or conf < rule["min_confidence"]:
            continue
        storms.add(storm)
        key = f"nx:{scenario_id}:{storm}"
        if session.scalar(select(Alert.id).where(Alert.dedupe_key == key)) is not None:
            continue  # acknowledged or snoozed: keep the user's decision
        label = "critical" if severity >= 0.8 else "high" if severity >= 0.65 else "medium"
        session.add(
            Alert(
                id=uuid5(NS, key),
                source_id="nexus",
                source_record_id=key,
                data_mode="live" if scenario_id is None else "synthetic",
                is_synthetic=scenario_id is not None,
                scenario_id=scenario_id,
                generator_version=FUSION_VERSION,
                available_at=now,
                kind="disruption",
                severity=label,
                title=e.title,
                body=(
                    f"{e.type.replace('_', ' ').lower()} forecast · {e.alert_level or 'alert'} · "
                    f"severity {severity:.2f} · fused confidence {conf:.2f} · {e.source_id}"
                ),
                entity_refs=[{"type": "port", "locode": c} for c in e.locodes],
                event_id=e.id,
                status="open",
                dedupe_key=key,
            )
        )
        raised += 1
    return raised
