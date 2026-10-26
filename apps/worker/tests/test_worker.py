"""Worker: two strikes, the outbox and jobs, and the AIS replay (integration; skipped without
a test database)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any, ClassVar

import pytest
from cportal_api.jobs import enqueue
from cportal_connectors.base import Connector
from cportal_connectors.canonical import scenario_uuid
from cportal_connectors.ingest import sync_data_sources
from cportal_connectors.live import LiveError, LiveHttp
from cportal_core.db import session_scope
from cportal_core.models import AisPositionLatest, DataSource, Job, OutboxEvent
from cportal_core.schemas.records import CountryIndicatorRecord, Record
from cportal_core.testing import TEST_URL, database_available, reset_database
from cportal_worker import outbox, sources
from cportal_worker.replay import AisReplay
from sqlalchemy import func, select

DS = "DS-TRADE-03"  # a live-mode source; its connector is replaced by fakes below


@pytest.fixture(scope="module", autouse=True)
def database() -> Iterator[None]:
    if not database_available():
        pytest.skip("no test database")
    reset_database()
    with session_scope(TEST_URL) as session:
        sync_data_sources(session)
    yield


class Failing(Connector):
    ds_id = DS
    title = "fake failing source"

    def live(self, http: LiveHttp) -> list[Record]:
        raise LiveError("indicators: HTTP 503")


class Working(Connector):
    ds_id = DS
    title = "fake working source"
    calls: ClassVar[int] = 0

    def live(self, http: LiveHttp) -> list[Record]:
        Working.calls += 1
        ctx = http.ctx()
        return [
            CountryIndicatorRecord(
                id=ctx.rid("country_indicator", "BGD:X:2025"),
                **ctx.lineage("BGD:X:2025"),
                country_iso3="BGD",
                indicator_code="X",
                indicator_name="test indicator",
                year=2025,
                value=1.0,
            )
        ]


def _use(monkeypatch: pytest.MonkeyPatch, connector: Connector) -> None:
    monkeypatch.setattr(sources, "connectors", lambda: {DS: connector})


def _state() -> DataSource:
    with session_scope(TEST_URL) as session:
        row = session.scalar(select(DataSource).where(DataSource.ds_id == DS))
        assert row is not None
        return row


def test_two_strikes_then_fallback_and_cool_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, Failing())
    assert sources.refresh(DS, database_url=TEST_URL).status == "failed"
    assert _state().failures == 1 and _state().effective_mode is None
    assert sources.refresh(DS, database_url=TEST_URL).status == "failed"
    state = _state()
    assert state.failures == 2 and state.effective_mode == "replay"  # registry fallback
    # Within the cool-down the source is not hit again.
    _use(monkeypatch, Working())
    assert sources.refresh(DS, database_url=TEST_URL).status == "skipped"
    assert Working.calls == 0
    with session_scope(TEST_URL) as session:
        topics = set(session.scalars(select(OutboxEvent.topic)))
    assert "source.degraded" in topics
    # After the cool-down a success restores live mode.
    with session_scope(TEST_URL) as session:
        row = session.scalar(select(DataSource).where(DataSource.ds_id == DS))
        assert row is not None and row.last_attempt_ts is not None
        row.last_attempt_ts -= sources.COOL_DOWN + timedelta(minutes=1)
    outcome = sources.refresh(DS, database_url=TEST_URL)
    assert outcome.status == "succeeded" and outcome.records == 1
    assert _state().failures == 0 and _state().effective_mode == "live"


def test_jobs_run_or_fail_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[dict[str, Any]] = []
    monkeypatch.setitem(
        outbox.JOB_HANDLERS, "scenario.run", lambda params, url: ran.append(params) or {"ok": 1}
    )
    with session_scope(TEST_URL) as session:
        what_if = enqueue(session, "c1.what_if", {"close_port": "BDCGP"}).job_id
    with session_scope(TEST_URL) as session:
        scenario = enqueue(session, "scenario.run", {"scenario": "baseline"}).job_id
    assert outbox.drain(TEST_URL) >= 2
    with session_scope(TEST_URL) as session:
        a, b = session.get(Job, what_if), session.get(Job, scenario)
        assert a is not None and a.status == "failed" and "M3" in (a.error or "")
        assert b is not None and b.status == "succeeded" and b.result == {"ok": 1}
    assert ran == [{"scenario": "baseline"}]
    assert outbox.drain(TEST_URL) == 0  # nothing left; handlers are idempotent


def test_ais_replay_writes_synthetic_positions() -> None:
    replay = AisReplay("baseline", speed=60, window_h=24, database_url=TEST_URL)
    replay.load()
    assert replay.visits
    written = replay.tick()
    assert written > 0
    with session_scope(TEST_URL) as session:
        rows = session.scalars(select(AisPositionLatest)).all()
    assert rows and all(r.is_synthetic and r.data_mode == "synthetic" for r in rows)
    assert {r.scenario_id for r in rows} == {scenario_uuid("baseline")}
    assert all(r.mmsi // 1_000_000 == 999 for r in rows)  # synthetic MID (A-012)
    # Every replayed vessel is somewhere between the sea entry and the Karnaphuli berths.
    with session_scope(TEST_URL) as session:
        outside = session.scalar(
            select(func.count())
            .select_from(AisPositionLatest)
            .where(
                func.not_(
                    func.ST_Within(
                        AisPositionLatest.geom, func.ST_MakeEnvelope(91.3, 20.5, 92.3, 22.5, 4326)
                    )
                )
            )
        )
    assert outside == 0
