"""Contract: every P0 source's committed sample parses into its declared canonical records.

The synthetic side of the contract (twins in `packages/sim`) is in tests/contract at the repo
root, which may import both packages.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

import pytest
from cportal_connectors.canonical import sample_bytes
from cportal_connectors.registry import connectors, registry
from cportal_core.enums import DataMode
from cportal_core.schemas.records import Record

P0 = sorted(d for d, e in registry().items() if e.get("tier") == "P0")
WIRED = sorted(d for d, c in connectors().items() if c.parsers)
# P0 sources without a real sample, and why; their contract runs on the synthetic twin only.
NO_REAL_SAMPLE = {"DS-NEWS-01": "GDELT DOC returns 429 from this network (A-013)"}
# Tables whose facts change over time must say when each fact became available (SC-01).
TIME_VARYING = {
    "article",
    "disruption_event",
    "port_call",
    "port_activity_daily",
    "zone_presence_daily",
    "satellite_observation",
    "weather_observation",
    "ais_position_latest",
    "port_state_snapshot",
}


@pytest.fixture(scope="module")
def replayed() -> dict[str, list[Record]]:
    return {ds_id: connectors()[ds_id].replay() for ds_id in WIRED}


def test_every_p0_source_has_a_contract() -> None:
    for ds_id in P0:
        c = connectors()[ds_id]
        assert c.parsers or c.checks or ds_id in NO_REAL_SAMPLE, f"{ds_id}: no parsers or checks"
        assert c.record_types or c.checks, f"{ds_id}: declares no canonical record types"


@pytest.mark.parametrize("ds_id", WIRED)
def test_replay_yields_declared_records(ds_id: str, replayed: dict[str, list[Record]]) -> None:
    records = replayed[ds_id]
    declared = set(connectors()[ds_id].record_types)
    assert records, f"{ds_id}: samples parsed to nothing"
    produced = {type(r) for r in records}
    assert produced <= declared, f"{ds_id}: undeclared types {produced - declared}"
    assert produced == declared, f"{ds_id}: declared but never produced {declared - produced}"


@pytest.mark.parametrize("ds_id", WIRED)
def test_replay_lineage(ds_id: str, replayed: dict[str, list[Record]]) -> None:
    for r in replayed[ds_id]:
        assert r.source_id == ds_id
        assert r.data_mode == DataMode.REPLAY and not r.is_synthetic and r.scenario_id is None
        if r.table in TIME_VARYING:
            assert isinstance(r.available_at, datetime), f"{ds_id} {r.table}: no available_at"


@pytest.mark.parametrize("ds_id", WIRED)
def test_replay_is_deterministic(ds_id: str, replayed: dict[str, list[Record]]) -> None:
    again = connectors()[ds_id].replay()
    assert [r.id for r in again] == [r.id for r in replayed[ds_id]]


def test_basemap_checks_pass_and_reject_garbage() -> None:
    c = connectors()["DS-GEO-07"]
    for name, check in c.checks.items():
        check(sample_bytes("DS-GEO-07", name))
        with pytest.raises((ValueError, KeyError)):
            check(b'{"tilejson": "2.0.0", "version": 7}')


def test_known_facts_survive_parsing(replayed: dict[str, list[Record]]) -> None:
    """Spot checks against facts in PROBE_REPORT and the samples."""
    locodes = {getattr(r, "locode", None) for r in replayed["DS-PORT-05"]}
    assert {"BDCGP", "BDMGL", "BDPAY"} <= locodes  # Payra is BDPAY (S2)
    ports = Counter(r.table for r in replayed["DS-PORT-05"])
    assert ports["port"] >= 3
    calls = [r for r in replayed["DS-PORT-07"] if r.table == "port_call"]
    merak = next(c for c in calls if (c.source_record_id or "").startswith("9636345"))
    assert merak.waiting_h == 48.0  # PRETTY MERAK: arrived 29/12, berthed 31/12 (CPA 2026-01-05)
    articles = replayed["DS-NEWS-03"]
    assert all(a.snippet is None or len(a.snippet) <= 300 for a in articles)  # copyright guardrail
