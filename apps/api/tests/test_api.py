"""API against a migrated, seeded PostGIS (skipped when none is up): envelope, badges, scope,
pagination, problem+json, jobs, the name-pack guardrail and the read-latency budget."""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cportal_api.deps import get_session
from cportal_api.main import create_app
from cportal_connectors.ingest import replay_source, sync_data_sources
from cportal_core.db import session_scope
from cportal_core.names import load_pack
from cportal_sim.seed import seed_scenario
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

URL = "postgresql+psycopg://cportal:cportal@localhost:5432/cportal_test"
REPO = Path(__file__).resolve().parents[3]
SOURCES = ["DS-PORT-05", "DS-PORT-08", "DS-PORT-07", "DS-PORT-01", "DS-AIS-02", "DS-WX-02"]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    engine = create_engine(URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except OperationalError:
        pytest.skip("no test database")
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(REPO / "db" / "alembic.ini"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={URL}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    with session_scope(URL) as session:
        sync_data_sources(session)
    for ds_id in SOURCES:
        with session_scope(URL) as session:
            replay_source(session, ds_id)
    seed_scenario("baseline", URL)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    engine.dispose()


def test_meta_and_brand(client: TestClient) -> None:
    body = client.get("/api/v1/meta").json()
    assert body["brand"] == "ShipperFast" and body["name_pack"] == "fictional"
    assert body["banner"] is None


def test_badges_follow_the_rows(client: TestClient) -> None:
    real = client.get("/api/v1/ports/BDCGP/calls", params={"scenario": "", "limit": 20}).json()
    assert real["meta"]["mode"] == "replay" and real["meta"]["scenario"] is None
    assert all(c["data_mode"] == "replay" for c in real["data"]["items"])
    synthetic = client.get(
        "/api/v1/ports/BDCGP/calls", params={"method": "sim", "limit": 20}
    ).json()
    assert synthetic["meta"]["mode"] == "synthetic" and synthetic["meta"]["scenario"] == "baseline"
    # Real PortWatch days and the scenario's synthetic days overlap: the badge says "mixed".
    mixed = client.get("/api/v1/ports/BDCGP/activity", params={"days": 120}).json()
    assert set(mixed["meta"]["modes"]) == {"replay", "synthetic"}
    assert mixed["meta"]["mode"] == "mixed"


def test_cursor_pagination(client: TestClient) -> None:
    first = client.get("/api/v1/ports/BDCGP/calls", params={"limit": 5}).json()["data"]
    assert len(first["items"]) == 5 and first["next_cursor"]
    second = client.get(
        "/api/v1/ports/BDCGP/calls", params={"limit": 5, "cursor": first["next_cursor"]}
    ).json()["data"]
    assert {c["id"] for c in first["items"]}.isdisjoint({c["id"] for c in second["items"]})


def test_port_state_positions_events_graph(client: TestClient) -> None:
    state = client.get("/api/v1/ports/BDCGP/state").json()
    assert state["meta"]["mode"] == "synthetic" and state["data"]["berth_occupancy"]
    real_state = client.get("/api/v1/ports/BDCGP/state", params={"scenario": ""}).json()
    assert real_state["meta"]["sources"] == ["DS-PORT-07"]  # the CPA report snapshot
    positions = client.get("/api/v1/vessels/positions").json()
    assert positions["data"]["type"] == "FeatureCollection" and positions["data"]["features"]
    events = client.get("/api/v1/events", params={"country": "BGD", "scenario": ""}).json()
    assert events["data"] and events["meta"]["mode"] == "replay"
    graph = client.get("/api/v1/graph", params={"industry": "garments"}).json()["data"]
    assert graph["nodes"] and graph["edges"]
    fictional = set(load_pack("fictional").names.values())
    assert {n["organization"] for n in graph["nodes"]} <= fictional


def test_problems_and_stubs(client: TestClient) -> None:
    missing = client.get("/api/v1/ports/XXXXX/state")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert client.get("/api/v1/ports/BDCGP/calls", params={"scenario": "nope"}).status_code == 404
    forecast = client.get("/api/v1/ports/BDCGP/forecast")
    assert forecast.status_code == 501 and forecast.json()["title"] == "Not Implemented"


def test_jobs_are_accepted_and_pollable(client: TestClient) -> None:
    accepted = client.post("/api/v1/graph/what-if", json={"close_port": "BDCGP", "days": 3})
    assert accepted.status_code == 202
    job = client.get(accepted.json()["poll"]).json()
    assert job["status"] == "queued" and job["kind"] == "c1.what_if"


def test_quality_view_uses_the_guarded_name(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the real-name pack active, adverse views still show fictional names (Q-05)."""
    from cportal_core import names

    monkeypatch.setattr(names, "load_pack", lambda pack=None: load_pack(pack or "bd_demo"))
    batches = client.get("/api/v1/quality/batches", params={"limit": 200}).json()["data"]
    real = {load_pack("bd_demo").names[k] for k in load_pack("bd_demo").real_keys}
    assert batches and not ({b["facility"] for b in batches} & real)


@pytest.mark.parametrize(
    "path",
    ["/api/v1/ports/BDCGP/calls", "/api/v1/vessels/positions", "/api/v1/graph", "/api/v1/events"],
)
def test_read_latency_budget(client: TestClient, path: str) -> None:
    """02 §11: interactive reads p95 < 300 ms (in-process client, local Postgres)."""
    client.get(path)  # warm up
    timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        assert client.get(path).status_code == 200
        timings.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 < 300, f"{path}: p95 {p95:.0f} ms"


def test_kpi_strip(client: TestClient) -> None:
    body = client.get("/api/v1/kpis").json()["data"]["kpis"]
    kpi = {k["key"]: k for k in body}
    assert list(kpi) == [
        "vessels_at_anchorage",
        "mean_wait_24h",
        "active_disruptions",
        "orders_at_risk",
        "co2e_week",
    ]
    assert kpi["vessels_at_anchorage"]["value"] > 0
    assert kpi["vessels_at_anchorage"]["meta"]["mode"] == "synthetic"
    assert kpi["co2e_week"]["value"] is None and "M5" in kpi["co2e_week"]["detail"]


def test_ws_live_streams_scenario_positions(client: TestClient) -> None:
    with client.websocket_connect("/ws/live?scenario=baseline") as ws:
        assert ws.receive_json()["type"] == "hello"
        snapshot = ws.receive_json()
    assert snapshot["type"] == "positions" and snapshot["features"]
    assert snapshot["scenario"] == "baseline" and snapshot["mode"] in ("synthetic", "mixed")


def test_active_shipments_exclude_delivered(client: TestClient) -> None:
    every = client.get("/api/v1/shipments", params={"limit": 500}).json()["data"]
    active = client.get("/api/v1/shipments", params={"limit": 500, "active": True}).json()["data"]
    assert {s["status"] for s in every} >= {"delivered", "in_transit"}
    assert active and not {s["status"] for s in active} & {"delivered", "cancelled"}


def test_replay_clock_ignores_newer_real_positions(client: TestClient) -> None:
    """Real positions newer than the replay must not freeze the clock (the socket's trigger)."""
    from cportal_api.live import positions_snapshot
    from cportal_core.models import AisPositionLatest
    from sqlalchemy import delete, false, func, select, update

    real = AisPositionLatest.is_synthetic == false()
    with session_scope(URL) as session:
        replay_source(session, "DS-AIS-01")
        session.execute(
            update(AisPositionLatest)
            .where(real)
            .values(ts=func.now() + text("'30 days'::interval"))
        )
    try:
        with Session(create_engine(URL)) as session:
            snapshot = positions_snapshot("baseline", session)
            replay_max = session.scalar(
                select(func.max(AisPositionLatest.ts)).where(AisPositionLatest.is_synthetic)
            )
        assert snapshot["mode"] == "mixed" and replay_max is not None
        assert snapshot["ts"] == replay_max.isoformat()
    finally:
        with session_scope(URL) as session:
            session.execute(delete(AisPositionLatest).where(real))
