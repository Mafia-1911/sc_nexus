"""C5 in the worker: inspect lots awaiting QC, forecast lot risk, raise impact alerts.

Per scenario, only when there is work: lots still in process, or no C5 predictions yet (a fresh
seed). The image gallery and few-shot banks come from `uv run c5 eval` on the host.
"""

from __future__ import annotations

import logging
from typing import Any

from cportal_c5 import pipeline
from cportal_core.db import session_scope
from cportal_core.models import Batch, Prediction, Scenario
from sqlalchemy import exists, select

log = logging.getLogger(__name__)


def refresh(database_url: str | None = None, force: bool = False) -> dict[str, Any]:
    with session_scope(database_url) as session:
        scenarios = session.execute(select(Scenario.key, Scenario.id)).all()
    out: dict[str, Any] = {}
    for key, sid in scenarios:
        with session_scope(database_url) as session:
            waiting = session.scalar(
                select(
                    exists().where(
                        Batch.scenario_id == sid,
                        Batch.lot_code.like("FG-%"),
                        Batch.status == "in_process",
                    )
                )
            )
            done = session.scalar(
                select(exists().where(Prediction.capability == "c5", Prediction.scenario_id == sid))
            )
            if not (force or waiting or not done):
                continue
            out[key] = pipeline.refresh(session, sid)
    log.info("c5 refreshed", extra={"scenarios": out})
    return out
