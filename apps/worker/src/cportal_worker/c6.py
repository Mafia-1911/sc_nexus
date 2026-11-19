"""C6 in the worker: after a tariff source ingests (outbox) and every 6 hours (the date rolls
over): mark current measures, detect changes, recompute the effective-rate matrix."""

from __future__ import annotations

import logging
from typing import Any

from cportal_c6 import store
from cportal_core.db import session_scope

log = logging.getLogger(__name__)

TARIFF_SOURCES = ("DS-TRADE-04", "DS-TRADE-05", "DS-TRADE-07", "DS-TRADE-08")


def refresh(database_url: str | None = None) -> dict[str, Any]:
    with session_scope(database_url) as session:
        out = store.refresh(session)
    log.info("c6 refresh", extra=out)
    return out
