"""C2 in the worker: news → events → C1 refresh → buffer recommendations (the M4 chain)."""

from __future__ import annotations

import logging
from typing import Any

from cportal_c2 import llm as c2_llm
from cportal_c2 import service as c2
from cportal_c2.store import window_start
from cportal_core.db import session_scope
from cportal_core.llm import OllamaProvider
from cportal_core.models import OutboxEvent
from cportal_nexus import buffer

from cportal_worker import c1, nexus

log = logging.getLogger(__name__)
NEWS_SOURCES = {"DS-NEWS-02", "DS-NEWS-03", "DS-NEWS-04"}


def process(database_url: str | None = None) -> dict[str, Any]:
    with session_scope(database_url) as session:
        counts = c2.process(session)
        if counts["events"]:
            session.add(
                OutboxEvent(topic="disruption.updated", payload={"capability": "c2", **counts})
            )
    refreshed = c1.refresh(None, database_url)  # events move C1 risk and TTR (C1-AC06)
    with session_scope(database_url) as session:
        recommendations = buffer.refresh(session)
    door = nexus.door_eta(database_url) if counts["events"] else {}
    log.info("c2 processed", extra={**counts, "recommendations": recommendations})
    return {**counts, "c1": refreshed, "recommendations": recommendations, "door_eta": door}


def llm(database_url: str | None = None, top: int = 8) -> dict[str, Any]:
    """Second opinions from the local LLM on the top-K articles (A-061), then re-process."""
    provider = OllamaProvider()
    if not provider.available():
        log.info("local LLM unreachable; rules only", extra={"model": provider.model})
        return {"skipped": f"{provider.model} unreachable at {provider.root}"}
    with session_scope(database_url) as session:
        stats = c2_llm.run(session, provider, window_start(), top)
    return {"llm": stats, **process(database_url)}
