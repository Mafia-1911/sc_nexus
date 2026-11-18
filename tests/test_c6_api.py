"""Contract tests for /api/v1/tariffs on the real samples (replayed, then refreshed by C6)."""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator

import pytest
from cportal_api.deps import get_session
from cportal_api.main import create_app
from cportal_c6 import store
from cportal_connectors.registry import connectors
from cportal_core.db import session_scope
from cportal_core.loader import upsert
from cportal_core.testing import TEST_URL, database_available, reset_database
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")
ON = "2026-11-18"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    import datetime as dt

    reset_database()
    with session_scope(TEST_URL) as s:
        for ds in ("DS-TRADE-04", "DS-TRADE-05", "DS-TRADE-06", "DS-TRADE-07", "DS-TRADE-08"):
            upsert(s, connectors()[ds].replay())
    with session_scope(TEST_URL) as s:
        store.refresh(s, dt.date(2026, 11, 18))
    engine = create_engine(TEST_URL)
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


def test_overview(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/overview").json()
    d = body["data"]
    assert d["as_of"] == ON
    assert [m["code"] for m in d["markets"]] == ["USA", "GBR", "EUN", "JPN", "CAN"]
    usa = d["markets"][0]
    assert usa["live_source"] == "DS-TRADE-05" and usa["current_measures"] > 0
    assert usa["data_mode"] == "replay"
    assert d["origins"][0] == {"iso3": "BGD", "name": "Bangladesh"}
    assert len(d["products"]) == 22 and {p["industry"] for p in d["products"]} == {
        "garments",
        "pharma",
    }
    statuses = {f["status"] for f in d["feeds"]}
    assert statuses == {"live", "manual", "missing"}
    assert any(f["id"] == "EU-TARIC" and f["todo"] for f in d["feeds"])
    assert body["meta"]["mode"] == "replay"


def test_matrix_cells_and_badge(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/matrix", params={"hs6": "610910"}).json()
    d = body["data"]
    assert d["precomputed"] is True and d["as_of"] == ON
    assert len(d["cells"]) == 5 * 7
    cell = {(c["market"], c["origin"]): c for c in d["cells"]}
    assert cell[("USA", "BGD")]["effective_pct_max"] == 26.5
    assert cell[("GBR", "BGD")]["effective_pct_max"] == 0.0
    assert cell[("EUN", "VNM")]["is_resolved"] is False
    # notes are sent once and referenced by index (the matrix is the page's biggest payload)
    notes = [d["notes"][i] for i in cell[("EUN", "BGD")]["note_ids"]]
    assert "preference assumes the rules of origin are met" in notes
    assert len(d["notes"]) == len(set(d["notes"]))
    assert body["meta"]["mode"] == "replay"
    assert set(body["meta"]["sources"]) >= {"DS-TRADE-05", "DS-TRADE-07", "DS-TRADE-04"}
    assert "not legal or customs advice" in body["meta"]["note"]


def test_matrix_filters(client: TestClient) -> None:
    d = client.get(
        "/api/v1/tariffs/matrix",
        params={"market": "usa,gbr", "origin": ["BGD", "VNM"], "industry": "pharma"},
    ).json()["data"]
    assert {c["market"] for c in d["cells"]} == {"USA", "GBR"}
    assert {c["origin"] for c in d["cells"]} == {"BGD", "VNM"}
    assert all(c["hs6"][:2] in {"29", "30", "39", "48", "76", "96"} for c in d["cells"])


def test_matrix_on_a_date_not_precomputed_is_computed(client: TestClient) -> None:
    d = client.get(
        "/api/v1/tariffs/matrix",
        params={"as_of": "2029-12-01", "hs6": "610910", "market": "EUN", "origin": "BGD"},
    ).json()["data"]
    assert d["precomputed"] is False
    (c,) = d["cells"]
    assert c["effective_pct_max"] == 12.0  # after the EBA transition (hand-kept, estimate)


def test_product_detail(client: TestClient) -> None:
    d = client.get(
        "/api/v1/tariffs/products/610910", params={"market": "USA", "origin": "BGD"}
    ).json()["data"]
    assert d["product"]["name"] == "Men's knitted cotton T-shirt"
    (usa,) = d["markets"]
    (line,) = usa["lines"]
    assert line["code"] == "61091000" and line["description"] == "Of cotton"
    assert line["effective_pct"] == 26.5
    roles = [c["role"] for c in line["components"]]
    assert roles[0] == "base" and "additional" in roles and "possible_exemption" in roles
    base = line["components"][0]
    assert base["source_url"].startswith("https://hts.usitc.gov/")


def test_product_badge_and_sources(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/products/610910").json()
    assert body["meta"]["mode"] == "replay"
    assert {"DS-TRADE-05", "DS-TRADE-07", "DS-TRADE-04", "DS-TRADE-08"} <= set(
        body["meta"]["sources"]
    )


def test_product_errors(client: TestClient) -> None:
    assert client.get("/api/v1/tariffs/products/61091").status_code == 422
    assert client.get("/api/v1/tariffs/products/999999").status_code == 404


def test_origin_relations(client: TestClient) -> None:
    d = client.get("/api/v1/tariffs/origins/bgd").json()["data"]
    schemes = {(s["market"], s["group_code"]) for s in d["schemes"]}
    assert ("GBR", "1062") in schemes and ("EUN", "EU-EBA") in schemes
    refs = {s["measure_ref"] for s in d["surcharges"]}
    assert {"9903.05.26", "9903.06.12"} <= refs
    assert client.get("/api/v1/tariffs/origins/BD").status_code == 422


def test_notices(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/notices", params={"kind": "trade_remedy"}).json()
    assert body["data"] and all(n["kind"] == "trade_remedy" for n in body["data"])
    dates = [n["publication_date"] for n in body["data"]]
    assert dates == sorted(dates, reverse=True)
    china = client.get("/api/v1/tariffs/notices", params={"country": "chn"}).json()["data"]
    assert china and all("CHN" in n["countries"] for n in china)
    assert client.get("/api/v1/tariffs/notices", params={"kind": "nope"}).status_code == 422


def test_changes_empty_on_a_single_snapshot(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/changes").json()
    assert body["data"] == [] and body["meta"]["mode"] == "none"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/tariffs/overview",
        "/api/v1/tariffs/matrix",
        "/api/v1/tariffs/products/610910",
        "/api/v1/tariffs/changes",
        "/api/v1/tariffs/notices",
        "/api/v1/tariffs/origins/BGD",
    ],
)
def test_read_latency_budget(client: TestClient, path: str) -> None:
    """AGENTS rule 7: interactive reads p95 < 300 ms (in-process client, local Postgres)."""
    client.get(path)
    timings = []
    for _ in range(20):
        t0 = time.perf_counter()
        assert client.get(path).status_code == 200
        timings.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 < 300, f"{path}: p95 {p95:.0f} ms"
