"""C4 in the worker: retrain and replace the replay predictions (daily, and after GFW ingests)."""

from __future__ import annotations

import logging
from typing import Any

from cportal_c4 import pipeline, store
from cportal_core.db import session_scope

from cportal_worker import nexus

log = logging.getLogger(__name__)
PORTS = ("BDCGP",)


def train(database_url: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for locode in PORTS:
        try:
            with session_scope(database_url) as session:
                run = pipeline.train(session, locode, ablation=False)
                out[locode] = store.refresh(session, run)
        except pipeline.NotEnoughHistory as exc:  # a fresh database has the 90-day sample only
            out[locode] = {"skipped": str(exc)}
    log.info("c4 trained", extra={"ports": out})
    out["nexus"] = nexus.refresh(database_url)  # new port-call predictions (NX-R01)
    return out
