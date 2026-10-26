"""C1 in the worker: keep each scenario's node metrics current, and run Monte Carlo what-ifs."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from cportal_c1 import service, store
from cportal_c1.schemas import WhatIfRequest
from cportal_core.db import session_scope
from cportal_core.models import OutboxEvent, Scenario
from sqlalchemy import select

log = logging.getLogger(__name__)


def refresh(
    scenario: str | None = None, database_url: str | None = None, *, force: bool = False
) -> dict[str, int | None]:
    """Recompute metrics for one scenario (or all) whose inputs changed since the last run."""
    with session_scope(database_url) as session:
        keys = [scenario] if scenario else list(session.scalars(select(Scenario.key)))
    written: dict[str, int | None] = {}
    for key in keys:
        with session_scope(database_url) as session:
            row = store.scenario_row(session, key)
            if row is None:
                continue
            written[key] = store.refresh(session, row, force=force)
            if written[key] is not None:
                session.add(
                    OutboxEvent(
                        topic="prediction.created",
                        payload={"capability": "c1", "scenario": key, "nodes": written[key]},
                    )
                )
                log.info("c1 metrics refreshed", extra={"scenario": key, "nodes": written[key]})
    return written


def what_if(
    params: dict[str, Any], database_url: str | None, job_id: UUID | None
) -> dict[str, Any]:
    """`c1.whatif` job: {"scenario": key, "request": WhatIfRequest}. Stores the result."""
    request = WhatIfRequest.model_validate(params["request"])
    with session_scope(database_url) as session:
        row = store.scenario_row(session, str(params["scenario"]))
        if row is None:
            raise ValueError(f"unknown scenario {params['scenario']!r}")
        graph = store.load(session, row)
        result = service.what_if(graph, request)
        whatif_id = store.save_whatif(session, row, result, graph.as_of, job_id)
    return {"whatif_id": str(whatif_id), "orders_late": result.orders_late}
