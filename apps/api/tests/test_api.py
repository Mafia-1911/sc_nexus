"""API against a migrated, seeded PostGIS (skipped when none is up): envelope, badges, scope,
pagination, problem+json, jobs, the name-pack guardrail and the read-latency budget."""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cportal_api.deps import get_session
from cportal_api.main import create_app
from cportal_c1 import store as c1_store
from cportal_c2 import service as c2_service
from cportal_c3 import store as c3_store
from cportal_c3.osm import RoadSegment
from cportal_c3.priors import load_priors as c3_priors
from cportal_connectors.ingest import replay_source, sync_data_sources
from cportal_core.db import session_scope
from cportal_core.models import Article, ModelVersion, Port, PortCall, Prediction
from cportal_core.names import load_pack
from cportal_nexus import buffer
from cportal_sim.seed import seed_scenario
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

URL = "postgresql+psycopg://cportal:cportal@localhost:5432/cportal_test"
REPO = Path(__file__).resolve().parents[3]
SOURCES = [
    "DS-PORT-05",
    "DS-PORT-08",
    "DS-PORT-07",
    "DS-PORT-01",
    "DS-AIS-02",
    "DS-WX-02",
    "DS-GEO-05",
]


def _toy_corridor() -> list[RoadSegment]:
    places = c3_priors().places
    xy = {k: (float(v["lon"]), float(v["lat"])) for k, v in places.items()}
    xy |= {"comilla": (91.18, 23.46), "meghna": (90.62, 23.60), "detour": (90.95, 23.20)}
    links = [
        ("BDCGP", "comilla", "trunk"), ("comilla", "meghna", "trunk"), ("meghna", "BDKAM", "trunk"),
        ("BDKAM", "tongi", "primary"), ("tongi", "gazipur", "primary"),
        ("comilla", "detour", "secondary"), ("detour", "narayanganj", "secondary"),
        ("narayanganj", "BDPGN", "secondary"), ("BDPGN", "BDKAM", "primary"),
        ("narayanganj", "tongi", "secondary"),
    ]  # fmt: skip
    ids = {k: i + 1 for i, k in enumerate(xy)}
    return [
        RoadSegment(1000 + i, ids[a], ids[b], hw, False, None, None, (xy[a], xy[b]))
        for i, (a, b, hw) in enumerate(links)
    ]


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
    with session_scope(URL) as session:  # what the worker's c1:refresh does
        c1_store.refresh(session, c1_store.scenario_row(session, "baseline"))  # type: ignore[arg-type]
    with session_scope(URL) as session:  # two outlets report one strike at Chattogram (C2)
        now = datetime.now(UTC)
        for i, (outlet, title) in enumerate(
            [
                ("port.example", "Chattogram port workers strike, container handling halted"),
                ("daily.example", "Strike at Chattogram port stalls exports for a second day"),
            ]
        ):
            session.add(
                Article(
                    url=f"https://{outlet}/strike-{i}",
                    url_canonical=f"https://{outlet}/strike-{i}",
                    source_name=outlet,
                    published_at=now - timedelta(hours=6 - i),
                    title=title,
                    snippet="Garment exporters warn of shipment delays as vessels wait.",
                    discovered_via="rss",
                    source_id="DS-NEWS-03",
                    data_mode="replay",
                    is_synthetic=False,
                )
            )
    with session_scope(URL) as session:  # what the worker's c2:process does
        c2_service.process(session)
        buffer.refresh(session)
    with session_scope(URL) as session:  # a toy corridor instead of the 340 MB OSM extract
        c3_store.save_edges(session, _toy_corridor(), "test")
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
    assert {n["organization"] for n in graph["nodes"] if n["organization"]} <= fictional
    assert {e["kind"] for e in graph["edges"]} == {"supply", "import", "export"}


def test_problems_and_stubs(client: TestClient) -> None:
    missing = client.get("/api/v1/ports/XXXXX/state")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert client.get("/api/v1/ports/BDCGP/calls", params={"scenario": "nope"}).status_code == 404
    forecast = client.get("/api/v1/ports/XXXXX/forecast")
    assert forecast.status_code == 404  # no C4 predictions for that port


def test_jobs_are_accepted_and_pollable(client: TestClient) -> None:
    body = {"disruptions": [{"node_id": "port:BDCGP", "duration_d": 3}], "mc_runs": 50}
    accepted = client.post("/api/v1/graph/whatif", json=body)
    assert accepted.status_code == 202
    job = client.get(accepted.json()["poll"]).json()
    assert job["status"] == "queued" and job["kind"] == "c1.whatif"


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
    [
        "/api/v1/ports/BDCGP/calls",
        "/api/v1/vessels/positions",
        "/api/v1/graph",
        "/api/v1/graph/critical",
        "/api/v1/events",
    ],
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


def test_c1_leaderboard_and_node_detail(client: TestClient) -> None:
    """C1-R01/R03/R04: ranked single points of failure, each with drivers and defaults."""
    body = client.get("/api/v1/graph/critical", params={"industry": "garments"}).json()
    items = body["data"]["items"]
    assert body["meta"]["mode"] == "synthetic" and body["meta"]["model_version"]
    assert items[0]["node_id"] == "port:BDCGP"  # every export crosses Chattogram
    mill_x = next(i for i in items if "Orivell" in i["name"])  # the planted denim SPOF
    assert items.index(mill_x) < 10 and mill_x["dominated_orders"] > 0
    assert mill_x["node_id"] in body["data"]["tts_below_ttr"]
    detail = client.get(f"/api/v1/graph/nodes/{mill_x['node_id']}").json()["data"]
    assert detail["metrics"]["risk_drivers"] and detail["dominated_orders"]
    assert "G-DENIM_FABRIC" in detail["customers"] and "G-COTTON_YARN" in detail["inputs"]
    assert detail["whatif_defaults"]["node_id"] == mill_x["node_id"]
    assert client.get("/api/v1/graph/nodes/nope").status_code == 404
    real_only = client.get("/api/v1/graph/critical", params={"scenario": ""})
    assert real_only.status_code == 404  # the network is synthetic: no scenario, no graph


def test_c1_whatif_runs_and_is_stored(client: TestClient) -> None:
    items = client.get("/api/v1/graph/critical").json()["data"]["items"]
    mill_x = next(i for i in items if "Orivell" in i["name"])
    body = {"disruptions": [{"node_id": mill_x["node_id"], "duration_d": 21}]}
    t0 = time.perf_counter()
    response = client.post("/api/v1/graph/whatif", json=body)
    assert response.status_code == 200 and time.perf_counter() - t0 < 2.0  # C1-AC04
    result = response.json()["data"]
    assert result["orders_late"] > 0 and result["timeline"] and result["mitigations"]
    assert result["tts_d"] is not None
    stored = client.get(f"/api/v1/graph/whatif/{result['id']}").json()["data"]
    assert stored["revenue_at_risk_usd"] == result["revenue_at_risk_usd"]
    bad = {"disruptions": [{"node_id": "port:XXXXX", "duration_d": 2}]}
    assert client.post("/api/v1/graph/whatif", json=bad).status_code == 404


def test_c1_views_keep_fictional_names_under_the_real_pack(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk is adverse (Q-05): the bd_demo pack never puts real names on the graph."""
    from cportal_core import names

    monkeypatch.setattr(names, "load_pack", lambda pack=None: load_pack(pack or "bd_demo"))
    nodes = client.get("/api/v1/graph").json()["data"]["nodes"]
    real = {load_pack("bd_demo").names[k] for k in load_pack("bd_demo").real_keys}
    assert nodes and not ({n["organization"] for n in nodes} & real)


def test_c2_events_carry_their_evidence(client: TestClient) -> None:
    """C2-R01/R02/R04: two outlets, one grounded event at Chattogram, with quotes."""
    events = client.get("/api/v1/events", params={"source": "news"}).json()
    [strike] = [e for e in events["data"] if e["type"] == "LABOR_STRIKE_BLOCKADE"]
    assert strike["locodes"] == ["BDCGP"] and strike["mentions"] == 2
    assert strike["confidence"] > 0.5  # two independent outlets corroborate
    detail = client.get(f"/api/v1/events/{strike['id']}").json()["data"]
    for m in detail["mentions"]:
        for start, end, quote in m["evidence"].values():
            assert m["text"][start:end] == quote  # every highlight is in the text
    assert detail["alerts"] and detail["alerts"][0]["status"] == "open"
    feeds = client.get("/api/v1/events", params={"source": "feeds", "scenario": ""}).json()
    assert all(e["source_id"] != "c2" for e in feeds["data"])


def test_c2_alerts_and_buffer_decisions(client: TestClient) -> None:
    """C2-AC08 / NX-R04: recommendations show units, cover, cost, value, confidence, evidence;
    a person accepts or dismisses them."""
    alerts = client.get("/api/v1/alerts").json()["data"]
    assert any("Chattogram" in a["title"] for a in alerts)
    recs = client.get("/api/v1/recommendations", params={"kind": "buffer"}).json()["data"]
    if not recs:
        pytest.skip("the strike makes no baseline order late: nothing to buffer")
    rec = recs[0]
    target = rec["targets"][0]
    assert target["units"] > 0 and target["days_of_cover"] > 0 and rec["expected_cost_usd"] >= 0
    assert rec["expected_benefit_usd"] > 0 and rec["confidence"] and rec["evidence_refs"]
    done = client.post(
        f"/api/v1/recommendations/{rec['id']}/decision",
        json={"decision": "dismissed", "feedback": "stock already in transit"},
    ).json()["data"]
    assert done["status"] == "dismissed" and done["decided_at"]
    ack = client.post(f"/api/v1/alerts/{alerts[0]['id']}/ack").json()["data"]
    assert ack["status"] == "ack"


def test_c3_route_plans(client: TestClient) -> None:
    """C3-AC02: Chattogram → Gazipur gives ≥ 3 plans, non-dominated first, in < 5 s."""
    places = client.get("/api/v1/routes/places").json()["data"]
    assert {"BDCGP", "gazipur", "BDKAM"} <= {p["key"] for p in places}
    rail = client.get("/api/v1/network/services", params={"mode": "rail"}).json()["data"]
    assert rail and rail[0]["origin"] == "BDCGP"
    body = {"origin": "BDCGP", "dest": "gazipur", "deadline": "2030-01-01T00:00:00Z"}
    t0 = time.perf_counter()
    response = client.post("/api/v1/routes/optimize", json=body)
    assert response.status_code == 200 and time.perf_counter() - t0 < 5
    result = response.json()["data"]
    plans = result["plans"]
    assert len(plans) >= 3 and plans[0]["pareto_rank"] == 0
    assert {"road", "rail", "barge"} <= {m for p in plans for m in p["modes"]}
    for p in plans:
        assert p["time_p50_h"] <= p["time_p90_h"] and p["legs"]
        assert all(leg["factor"]["source"] for leg in p["legs"] if leg["mode"] != "transfer")
    stored = client.get(f"/api/v1/routes/{result['request_id']}").json()["data"]
    assert len(stored["options"]) == len(plans)
    assert (
        client.post("/api/v1/routes/optimize", json={"origin": "BDCGP", "dest": "mars"}).status_code
        == 404
    )


def test_c4_port_predictions(client: TestClient) -> None:
    """C4 §8: the queue fan, vessels in port with departure windows, one vessel's track.

    The 90-day GFW sample is too short for C4's split, so stored predictions are written here
    the way `c4 train` writes them (the pipeline itself is tested in packages/c4_port_dwell)."""
    assert client.get("/api/v1/ports/BDMGL/predictions").json()["data"] == []
    snaps = [datetime(2026, 9, d, 6, tzinfo=UTC) for d in (1, 2)]
    with session_scope(URL) as session:
        port = session.scalar(select(Port).where(Port.locode == "BDCGP"))
        assert port is not None
        call = session.scalars(
            select(PortCall).where(PortCall.port_id == port.id, PortCall.method == "gfw")
        ).first()
        assert call is not None and call.arrival_ts is not None
        lineage = {"source_id": "c4", "data_mode": "replay", "is_synthetic": False}
        model = ModelVersion(
            **lineage, capability="c4", name="c4-dwell-lgbm-cqr (BDCGP)", version="t",
            metrics={"mae_gain_cargo": 0.18}, is_active=True,
        )  # fmt: skip
        session.add(model)
        session.flush()
        band = {"p10": 10.0, "p50": 30.0, "p90": 90.0}
        drivers = [{"feature": "n_present", "label": "Vessels in port", "value": "140",
                    "effect_pct": 12.0}]  # fmt: skip
        session.add(
            Prediction(
                **lineage, source_record_id=f"BDCGP:call:{call.id}", capability="c4",
                target_type="port_call", target_id=call.id, as_of=call.arrival_ts,
                quantiles=band, model_version_id=model.id,
                explanation={"drivers": drivers, "baseline": [8.0, 40.0, 120.0]},
            )
        )  # fmt: skip
        for i, at in enumerate(snaps):
            session.add(
                Prediction(
                    **lineage, source_record_id=f"BDCGP:call:{call.id}:{at.isoformat()}",
                    capability="c4", target_type="port_call_remaining", target_id=call.id,
                    as_of=at, value=20.0 - i, quantiles={"p10": 5.0, "p50": 20.0 - i, "p90": 60.0},
                    explanation={"elapsed_h": 24.0 + 24 * i},
                )
            )  # fmt: skip
            session.add(
                Prediction(
                    **lineage, source_record_id=f"BDCGP:queue:{at.isoformat()}",
                    capability="c4", target_type="port_queue", target_id=port.id, as_of=at,
                    quantiles=band,
                    dist_params={"history": [["2026-08-31", 110.0]],
                                 "forecast": [[f"2026-09-0{d}", 90.0, 100.0, 120.0]
                                              for d in range(2, 9)]},
                )
            )  # fmt: skip
    t0 = time.perf_counter()
    fan = client.get("/api/v1/ports/BDCGP/forecast", params={"horizon_d": 3})
    assert fan.status_code == 200 and time.perf_counter() - t0 < 0.3
    body = fan.json()
    assert body["meta"]["mode"] == "replay" and "DS-AIS-02" in body["meta"]["sources"]
    data = body["data"]
    assert data["as_of"].startswith("2026-09-02") and len(data["snapshots"]) == 2
    assert len(data["forecast"]) == 3 and data["metrics"]["c4-dwell-lgbm-cqr"]["mae_gain_cargo"]
    early = client.get("/api/v1/ports/BDCGP/predictions", params={"as_of": "2026-09-01T12:00:00Z"})
    vessels = early.json()["data"]
    assert len(vessels) == 1
    v = vessels[0]
    assert v["dwell_at_arrival"] == band and v["baseline_at_arrival"]["p50"] == 40.0
    assert v["departure_p10"] < v["departure_p50"] < v["departure_p90"]
    assert v["drivers"][0]["label"] == "Vessels in port"
    track = client.get(f"/api/v1/vessels/{v['vessel_id']}/prediction").json()["data"]
    assert [u["as_of"][:10] for u in track["updates"]] == ["2026-09-01", "2026-09-02"]
    assert client.get(f"/api/v1/vessels/{call.id}/prediction").status_code == 404


def test_c5_quality_lab(client: TestClient) -> None:
    """C5 §8: lots get AQL decisions, a failed lot gets costed options (C5-AC06), lines get risk
    and SPC. The gallery rows stand in for `c5 eval` (lot inspection needs no image files)."""
    from cportal_c5 import pipeline
    from cportal_core.models import InspectionImage, InspectionResult, Scenario

    with session_scope(URL) as session:
        sid = session.scalar(select(Scenario.id).where(Scenario.key == "baseline"))
        assert sid is not None
        for i in range(40):
            defect = i % 4 == 0  # 10 defect images; the model misses 2 of them
            img = InspectionImage(
                source_id="DS-VIS-04", data_mode="replay", is_synthetic=False, category="stitch",
                split="test", label="stain_damage" if defect else "good",
                uri=f"gallery/stitch/{i}.jpg", source_dataset="StitchNet v2 (Roboflow)",
            )  # fmt: skip
            session.add(img)
            session.flush()
            session.add(
                InspectionResult(
                    source_id="c5", data_mode="replay", is_synthetic=False, image_id=img.id,
                    image_score=0.3 if defect else 0.05, is_anomalous=defect and i % 20 != 0,
                    threshold=0.1, heatmap_uri=f"gallery/stitch/{i}_heat.png",
                )
            )  # fmt: skip
        session.flush()
        result = pipeline.refresh(session, sid)
    assert result["inspected"].get("garments:reject", 0) > 0
    summary = client.get("/api/v1/quality/summary").json()
    assert summary["meta"]["mode"] == "synthetic" and summary["data"]["rejected"] > 0
    rejected = client.get("/api/v1/quality/batches", params={"status": "rejected"}).json()["data"]
    assert rejected and all(r["decision"] == "reject" for r in rejected)
    with_alert = next(r for r in rejected if r["alert_id"])
    detail = client.get(f"/api/v1/quality/batches/{with_alert['id']}").json()["data"]
    assert detail["aql"]["sample_size"] == 125 and detail["aql"]["accept"] == 7
    assert len(detail["recommendations"]) >= 2
    for rec in detail["recommendations"]:
        assert rec["expected_cost_usd"] is not None and rec["expected_benefit_usd"] is not None
    assert detail["items"] and detail["items"][0]["flagged"]  # flagged items first
    lines = client.get("/api/v1/quality/lines").json()["data"]
    assert lines and 0 <= lines[0]["p_fail_next"] <= 1
    spc = client.get(f"/api/v1/quality/lines/{lines[0]['id']}/spc").json()["data"]
    assert spc["points"] and spc["center"] > 0
    assert client.get("/api/v1/quality/files/../../.env").status_code == 404
    bad = client.post(
        "/api/v1/quality/inspections",
        files={"image": ("x.png", b"\x89PNG", "image/png")},
        data={"category": "no-such-category"},
    )
    assert bad.status_code == 404
