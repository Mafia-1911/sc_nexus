"""One C5 refresh per scenario: inspect waiting lots, forecast lot risk, raise impact alerts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from cportal_c5 import impact, lots, risk, store


def refresh(session: Session, scenario_id: UUID) -> dict[str, Any]:
    inspected = lots.inspect(session, scenario_id)
    session.flush()
    history = risk.load_lots(session, scenario_id)
    return {
        "inspected": inspected,
        "risk": store.save_risk(session, scenario_id, history),
        "impact": impact.refresh(session, scenario_id),
    }
