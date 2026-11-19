"""C6 in the worker: a tariff ingest's outbox event refreshes the matrix through the dispatcher."""

from __future__ import annotations

import pytest
from cportal_connectors.registry import connectors
from cportal_core.db import session_scope
from cportal_core.loader import upsert
from cportal_core.models import OutboxEvent, TariffEffectiveRate
from cportal_core.testing import TEST_URL, database_available, reset_database
from cportal_worker import outbox
from cportal_worker.main import build_scheduler
from sqlalchemy import func, select

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")


def test_tariff_ingest_event_refreshes_the_matrix() -> None:
    reset_database()
    with session_scope(TEST_URL) as s:
        for ds in ("DS-TRADE-04", "DS-TRADE-05", "DS-TRADE-07", "DS-TRADE-08"):
            upsert(s, connectors()[ds].replay())
        assert s.scalar(select(func.count()).select_from(TariffEffectiveRate)) == 0
        s.add(OutboxEvent(topic="source.ingested", payload={"ds_id": "DS-TRADE-05", "rows": 1}))
    assert outbox.drain(TEST_URL) == 1
    with session_scope(TEST_URL) as s:
        assert s.scalar(select(func.count()).select_from(TariffEffectiveRate)) == 5 * 22 * 7
        processed = s.scalar(
            select(OutboxEvent.processed_at).where(OutboxEvent.topic == "source.ingested")
        )
        assert processed is not None


def test_c6_refresh_is_scheduled() -> None:
    ids = {j.id for j in build_scheduler(live=False, replay=None).get_jobs()}
    assert "c6:refresh" in ids
    assert "c6.refresh" in outbox.JOB_HANDLERS
