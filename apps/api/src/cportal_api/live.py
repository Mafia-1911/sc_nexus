"""Position snapshots for `/ws/live` (sync DB access, run in a worker thread)."""

from __future__ import annotations

from typing import Any

from cportal_core.models import AisPositionLatest, Scenario, Vessel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cportal_api.deps import Scope
from cportal_api.geo import feature


def positions_snapshot(scenario: str | None, session: Session) -> dict[str, Any]:
    session.rollback()  # end the last snapshot's transaction: no idle-in-transaction socket
    scenario_id = (
        session.scalar(select(Scenario.id).where(Scenario.key == scenario)) if scenario else None
    )
    scope = Scope(scenario if scenario_id else None, scenario_id)
    newest = session.scalar(
        select(func.max(AisPositionLatest.ts)).where(scope.rows(AisPositionLatest))
    )
    rows = session.execute(
        select(AisPositionLatest, Vessel.name, Vessel.ship_type_group)
        .outerjoin(Vessel, Vessel.id == AisPositionLatest.vessel_id)
        .where(scope.rows(AisPositionLatest))
    ).all()
    features = [
        feature(
            p.geom,
            {
                "mmsi": p.mmsi,
                "name": name,
                "type": group,
                "ts": p.ts.isoformat(),
                "sog_kn": p.sog_kn,
                "cog_deg": p.cog_deg,
                "nav_status": p.nav_status,
                "data_mode": p.data_mode,
            },
        )
        for p, name, group in rows
    ]
    modes = sorted({str(p.data_mode) for p, _, _ in rows})
    return {
        "type": "positions",
        "scenario": scope.key,
        "ts": newest.isoformat() if newest else None,
        "mode": modes[0] if len(modes) == 1 else ("mixed" if modes else "none"),
        "features": features,
    }
