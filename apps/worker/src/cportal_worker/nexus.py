"""Nexus in the worker: evidence fusion, then door ETA (08 §1, §3; NX-R01, NX-R03).

Runs on a timer, after C2 turns news into disruption events and after C4 retrains (new port-call
predictions). Fusion runs first so door ETAs hold shipments with the fused confidence. Scopes:
real events (now = the clock) and each scenario (now = its start).
"""

from __future__ import annotations

import logging
from typing import Any

from cportal_core.db import session_scope
from cportal_core.models import Scenario
from cportal_nexus import fusion, tracker
from sqlalchemy import select

log = logging.getLogger(__name__)


def refresh(database_url: str | None = None) -> dict[str, Any]:
    with session_scope(database_url) as session:
        out: dict[str, Any] = {"real": {"fusion": fusion.refresh(session, None)}}
        scenarios = session.scalars(select(Scenario)).all()
        keys = [(sc.key, sc.id, tracker.scenario_now(sc)) for sc in scenarios]
    for key, sid, now in keys:
        with session_scope(database_url) as session:
            out[key] = {"fusion": fusion.refresh(session, sid, now)}
        with session_scope(database_url) as session:
            out[key]["door_eta"] = tracker.refresh(session, sid)
    log.info("nexus refreshed", extra={"scopes": out})
    return out
