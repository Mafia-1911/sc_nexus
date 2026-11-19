"""Contract tests for /api/v1/tariffs on the real samples (replayed, then refreshed by C6)."""

from __future__ import annotations

import datetime as dt
import statistics
import time
from collections.abc import Iterator

import pytest
from cportal_api.deps import get_session
from cportal_api.main import create_app
from cportal_c2 import service as c2_service
from cportal_c6 import store
from cportal_connectors.registry import connectors
from cportal_core.db import session_scope
from cportal_core.enums import DataMode, DiscoveredVia
from cportal_core.ids import stable_id
from cportal_core.loader import upsert
from cportal_core.schemas.records import ArticleRecord
from cportal_core.testing import TEST_URL, database_available, reset_database
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")
ON = "2026-11-18"


def _article(i: int, title: str, day: int, outlet: str) -> ArticleRecord:
    url = f"https://{outlet}/tariff-{i}"
    return ArticleRecord(
        id=stable_id("article", "test", url),
        source_id="DS-NEWS-03",
        source_record_id=url,
        data_mode=DataMode.REPLAY,
        url=url,
        url_canonical=url,
        source_name=outlet,
        published_at=dt.datetime(2026, 11, day, 8, tzinfo=dt.UTC),
        lang="en",
        title=title,
        discovered_via=DiscoveredVia.RSS,
        feed_id=outlet,
        available_at=dt.datetime(2026, 11, day, 8, tzinfo=dt.UTC),
    )


# Test articles (written for this test, not real news): a cut, reported twice, and a raise.
NEWS = [
    _article(
        1,
        "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent",
        12,
        "a.example",
    ),
    _article(
        2,
        "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 "
        "percent, exporters say",
        12,
        "b.example",
    ),
    _article(
        3,
        "Bangladesh garments to lose duty-free access to the EU after LDC graduation",
        15,
        "c.example",
    ),
]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    reset_database()
    with session_scope(TEST_URL) as s:
        for ds in ("DS-TRADE-04", "DS-TRADE-05", "DS-TRADE-06", "DS-TRADE-07", "DS-TRADE-08"):
            upsert(s, connectors()[ds].replay())
    with session_scope(TEST_URL) as s:
        store.refresh(s, dt.date(2026, 11, 18))
        upsert(s, NEWS)
    with session_scope(TEST_URL) as s:
        c2_service.process(s, now=dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC))
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
    tee = next(p for p in d["products"] if p["hs6"] == "610910")
    assert tee["key"] == "TSHIRT"  # the industry-pack SKU, so pages can map orders to HS codes
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


def test_product_components_name_the_scheme(client: TestClient) -> None:
    d = client.get(
        "/api/v1/tariffs/products/610910", params={"market": "GBR", "origin": "BGD"}
    ).json()["data"]
    (line,) = d["markets"][0]["lines"]
    (pref,) = [c for c in line["components"] if c["role"] == "preference"]
    assert pref["origin_code"] == "1062"
    assert "Comprehensive" in pref["origin_name"]  # UK DCTS Comprehensive Preferences
    base = next(c for c in line["components"] if c["role"] == "base")
    assert base["origin_name"] == "All origins"


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
        "/api/v1/tariffs/news",
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


def test_news_carries_the_tariff_signal(client: TestClient) -> None:
    body = client.get("/api/v1/tariffs/news").json()
    items = body["data"]
    cut = next(n for n in items if n["direction"] == "cut")
    assert (cut["markets"], cut["origins"]) == (["USA"], ["BGD"])
    assert (cut["rate_pct"], cut["previous_pct"]) == (10.0, 20.0)
    assert cut["reports"] == 2 and cut["industries"] == ["garments"]
    assert cut["confirmed"] is False and cut["confirmation"] is None
    assert cut["label"] == "announced, not in the schedule yet"
    assert cut["url"].startswith("https://") and cut["published"].startswith("2026-11-12")
    lose = next(n for n in items if n["direction"] == "raise")
    assert lose["markets"] == ["EUN"] and lose["origins"] == ["BGD"]
    dates = [n["published"] for n in items]
    assert dates == sorted(dates, reverse=True)
    assert body["meta"]["mode"] == "replay"


def test_news_filters(client: TestClient) -> None:
    usa = client.get("/api/v1/tariffs/news", params={"market": "usa"}).json()["data"]
    assert usa and all("USA" in n["markets"] for n in usa)
    assert client.get("/api/v1/tariffs/news", params={"origin": "VNM"}).json()["data"] == []


def test_news_by_event(client: TestClient) -> None:
    items = client.get("/api/v1/tariffs/news").json()["data"]
    linked = next(n for n in items if n["event_id"])  # the cut story is also a C2 event
    one = client.get("/api/v1/tariffs/news", params={"event_id": linked["event_id"]}).json()
    assert [n["id"] for n in one["data"]] == [linked["id"]]
    assert client.get("/api/v1/tariffs/news", params={"event_id": "nope"}).status_code == 422


def test_overview_counts_news(client: TestClient) -> None:
    d = client.get("/api/v1/tariffs/overview").json()["data"]
    assert d["news_30d"] >= 2


def test_a_schedule_change_confirms_matching_news(client: TestClient) -> None:
    """Runs last: plants a US raise for Bangladesh (+5 pp) and a raise story; the story turns
    'confirmed', the earlier cut story does not (the directions disagree)."""
    import json

    from cportal_connectors.canonical import ParseContext, sample_bytes
    from cportal_connectors.parsers.tariffs import hts_parser

    rows = json.loads(sample_bytes("DS-TRADE-05", "hts_export_9903_01_07.json"))
    (target,) = [r for r in rows if r["htsno"] == "9903.05.26"]
    target["general"] = "The duty provided in the applicable subheading + 15%"
    later = ParseContext(
        "DS-TRADE-05", DataMode.LIVE, fetched_at=dt.datetime(2026, 11, 19, 6, tzinfo=dt.UTC)
    )
    with session_scope(TEST_URL) as s:
        upsert(s, hts_parser("hts:9903.01-9903.07")(json.dumps(rows).encode(), later))
        upsert(
            s,
            [
                _article(
                    4,
                    "US raises tariff on Bangladesh garments to 15 percent from 10 percent",
                    16,
                    "d.example",
                )
            ],
        )
    with session_scope(TEST_URL) as s:
        store.refresh(s, dt.date(2026, 11, 18))
        c2_service.process(s, now=dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC))
    items = client.get("/api/v1/tariffs/news", params={"market": "USA"}).json()["data"]
    raised = next(n for n in items if n["direction"] == "raise")
    assert raised["confirmed"] is True and raised["label"] == "in the schedule"
    assert raised["confirmation"]["measure_ref"] == "9903.05.26"
    assert raised["confirmation"]["delta_pp"] == 5.0
    cut = next(n for n in items if n["direction"] == "cut")
    assert cut["confirmed"] is False


def test_brief_has_a_cited_tariff_line(client: TestClient) -> None:
    """Runs after the planted change: the Control Tower brief names it and cites the rows."""
    lines = client.get("/api/v1/brief", params={"scenario": ""}).json()["data"]["lines"]
    (line,) = [ln for ln in lines if ln["text"].startswith("Tariffs")]
    assert "9903.05.26" in line["text"] and "Bangladesh" in line["text"]
    assert "+10% → +15%" in line["text"]
    assert line["tone"] == "watch"  # a duty on Bangladesh went up
    kinds = {c["kind"] for c in line["cites"]}
    assert kinds == {"tariff"} and all(c["href"].startswith("/tariffs") for c in line["cites"])


@pytest.mark.parametrize(
    "params",
    [
        {"industry": "pharma", "hs6": "610910"},  # a garment code asked within pharma
        {"industry": "no-such-industry"},
    ],
)
def test_matrix_filters_never_widen_to_everything(client: TestClient, params: dict) -> None:
    """Review 2026-11-19 #4: a filter that matches nothing returns nothing, not the matrix."""
    for as_of in ("2026-11-18", "2026-06-01"):  # precomputed and on-the-fly paths
        r = client.get("/api/v1/tariffs/matrix", params={**params, "as_of": as_of})
        assert r.status_code == 200 and r.json()["data"]["cells"] == [], (params, as_of)


def test_origin_relations_badge_and_date(client: TestClient) -> None:
    """Review 2026-11-19 #8: a badge from the rows, and as_of filters schemes and surcharges."""
    body = client.get("/api/v1/tariffs/origins/BGD", params={"as_of": "2026-11-18"}).json()
    # from the rows (an earlier test in this module plants a live row: then "mixed"), never "none"
    assert body["meta"]["mode"] in {"replay", "mixed"} and body["meta"]["modes"]
    assert "DS-TRADE-05" in body["meta"]["sources"]
    assert ("EUN", "EU-EBA") in {(s["market"], s["group_code"]) for s in body["data"]["schemes"]}
    later = client.get("/api/v1/tariffs/origins/BGD", params={"as_of": "2030-01-01"}).json()
    assert ("EUN", "EU-EBA") not in {
        (s["market"], s["group_code"]) for s in later["data"]["schemes"]
    }  # EBA ends at LDC graduation (2029-11-24)
