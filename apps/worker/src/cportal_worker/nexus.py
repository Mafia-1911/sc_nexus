"""Nexus in the worker: door ETA for every open shipment (08 §1, NX-R01).

Runs on a timer, after C2 turns news into disruption events and after C4 retrains (new port-call
predictions), so door ETAs follow both.
"""

from __future__ import annotations

import logging
from typing import Any

from cportal_core.db import session_scope
from cportal_core.models import Scenario
from cportal_nexus import tracker
from sqlalchemy import select

log = logging.getLogger(__name__)


def door_eta(database_url: str | None = None) -> dict[str, Any]:
    with session_scope(database_url) as session:
        scenarios = session.execute(select(Scenario.key, Scenario.id)).all()
    out: dict[str, Any] = {}
    for key, sid in scenarios:
        with session_scope(database_url) as session:
            out[key] = tracker.refresh(session, sid)
    log.info("door eta refreshed", extra={"scenarios": out})
    return out
