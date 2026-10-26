"""Contract (02 §12): for every DS-ID, parse(real sample) and its synthetic twin land in the same
canonical records, with the same columns, types and units.

Twins render each source's own wire format and go through the source's real parser, so this
test checks the twin end of that loop: lineage, declared record types, and a units sanity
check (twin medians within 10× of the real replay's medians catches km/h vs m/s, tonnes vs kg,
hours vs days).
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

import pytest
from cportal_connectors.canonical import scenario_uuid
from cportal_connectors.registry import connectors, registry
from cportal_core.enums import DataMode
from cportal_core.schemas.records import Record
from cportal_sim import twins
from cportal_sim.port_des import DesResult, simulate
from cportal_sim.scenarios import cyclone_stories, load_scenario

SCENARIO = "contract_twins"
NOW = datetime(2026, 10, 26, tzinfo=UTC)


@pytest.fixture(scope="module")
def des() -> DesResult:
    return simulate(NOW - timedelta(days=10), NOW + timedelta(days=2), seed=5)


@pytest.fixture(scope="module")
def cyclone() -> dict[str, object]:
    spec = load_scenario("cyclone_supplier_delay")
    assert spec.cyclone is not None
    return spec.cyclone


def twin_outputs(des: DesResult, cyclone: dict[str, object]) -> dict[str, list[Record]]:
    spec = load_scenario("cyclone_supplier_delay")
    stories = cyclone_stories(spec, cyclone)  # type: ignore[arg-type]
    return {
        "DS-AIS-01": twins.aisstream(des, SCENARIO, hour=NOW - timedelta(hours=1)),
        "DS-AIS-02": twins.gfw_port_visits(des, SCENARIO, until=NOW)
        + twins.gfw_presence(des, SCENARIO, until=NOW),
        "DS-SAT-04": twins.gfw_sar(des, SCENARIO, until=NOW, every_days=2),
        "DS-PORT-01": twins.portwatch(des, SCENARIO, until=NOW, cyclone=cyclone),  # type: ignore[arg-type]
        "DS-WX-01": twins.open_meteo(SCENARIO, "ctg_port", 22.32, 91.77, NOW, 48, False, NOW)
        + twins.open_meteo(SCENARIO, "ctg_anchorage", 22.04, 91.71, NOW, 48, True, NOW),
        "DS-WX-02": twins.gdacs(SCENARIO, cyclone),  # type: ignore[arg-type]
        "DS-NEWS-01": twins.gdelt_doc(SCENARIO, stories),
        "DS-NEWS-02": twins.gdelt_gkg(SCENARIO, stories),
        "DS-NEWS-03": twins.rss(SCENARIO, stories),
        "DS-NEWS-04": twins.reliefweb(SCENARIO, stories, disaster="Bangladesh: Cyclone SYN-01"),
        "DS-PHARMA-01": twins.openfda_recall(
            SCENARIO, "Synthora Actives", "Amoxicillin trihydrate (API)", "Class II", NOW
        ),
    }


@pytest.fixture(scope="module")
def outputs(des: DesResult, cyclone: dict[str, object]) -> dict[str, list[Record]]:
    return twin_outputs(des, cyclone)


def test_every_source_that_falls_back_to_synthetic_has_a_twin(
    outputs: dict[str, list[Record]],
) -> None:
    needed = {
        ds_id
        for ds_id, entry in registry().items()
        if entry.get("tier") == "P0" and "synthetic" in (entry.get("mode"), entry.get("fallback"))
    }
    assert needed <= set(outputs), f"missing twins: {needed - set(outputs)}"


@pytest.mark.parametrize(
    "ds_id",
    [
        "DS-AIS-01", "DS-AIS-02", "DS-SAT-04", "DS-PORT-01", "DS-WX-01", "DS-WX-02",
        "DS-NEWS-01", "DS-NEWS-02", "DS-NEWS-03", "DS-NEWS-04", "DS-PHARMA-01",
    ],
)  # fmt: skip
def test_twin_lineage_and_types(ds_id: str, outputs: dict[str, list[Record]]) -> None:
    records = outputs[ds_id]
    assert records, f"{ds_id}: twin produced nothing"
    declared = set(connectors()[ds_id].record_types)
    assert {type(r) for r in records} <= declared
    for r in records:
        assert r.source_id == ds_id
        assert r.data_mode == DataMode.SYNTHETIC and r.is_synthetic
        assert r.scenario_id == scenario_uuid(SCENARIO)
        assert r.generator_version and r.generator_version.startswith("cportal-sim/")


def _medians(records: list[Record]) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], list[float]] = {}
    for r in records:
        for name, value in r.row().items():
            if isinstance(value, int | float) and not isinstance(value, bool):
                values.setdefault((r.table, name), []).append(float(value))
    return {k: statistics.median(v) for k, v in values.items() if v}


UNIT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "DS-AIS-02": [("port_call", "dwell_h"), ("zone_presence_daily", "hours")],
    "DS-PORT-01": [("port_activity_daily", "calls_total")],
    "DS-SAT-04": [("satellite_observation", "detections_count")],
    "DS-WX-01": [
        ("weather_observation", "temperature_2m_c"),
        ("weather_observation", "wind_speed_10m_kmh"),
        ("weather_observation", "pressure_msl_hpa"),
        ("weather_observation", "wave_height_m"),
        ("weather_observation", "wave_period_s"),
    ],
}


@pytest.mark.parametrize("ds_id", sorted(UNIT_FIELDS))
def test_twin_units_match_real(ds_id: str, outputs: dict[str, list[Record]]) -> None:
    real = _medians(connectors()[ds_id].replay())
    synth = _medians(outputs[ds_id])
    for key in UNIT_FIELDS[ds_id]:
        assert key in real and key in synth, f"{ds_id} {key}: missing on one side"
        r, s = real[key], synth[key]
        if r == 0 or s == 0:
            continue
        ratio = s / r
        assert 0.1 <= ratio <= 10, f"{ds_id} {key}: twin {s} vs real {r} (ratio {ratio:.2f})"


def test_synthetic_text_names_no_real_firm(outputs: dict[str, list[Record]]) -> None:
    """Rule 3: synthetic articles and events mention fictional firms only."""
    from cportal_core.names import load_pack

    real_names = [load_pack("bd_demo").names[k] for k in load_pack("bd_demo").real_keys]
    texts: list[str] = []
    for records in outputs.values():
        for r in records:
            row = r.row()
            texts += [str(row.get(k) or "") for k in ("title", "summary", "snippet")]
    for name in real_names:
        assert not any(name in t for t in texts), name
