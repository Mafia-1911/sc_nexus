"""Contract: the synthetic AIS twin emits frames shaped exactly like real aisstream frames.

Real fixtures are the five-frame format samples in data/samples/DS-AIS-01/ (02-architecture.md
§12: real sample and synthetic output must validate against the same schema).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from cportal_connectors import ais_synthetic as synth
from cportal_connectors.aisstream import decode, position

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "data" / "samples" / "DS-AIS-01"
PRIORS = yaml.safe_load((REPO / "config" / synth.PRIORS).read_text())
WINDOW_END = datetime(2026, 10, 20, tzinfo=UTC)


def shape(value: Any) -> Any:
    """Keys and JSON types, recursively; numbers collapse to 'number'."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def real_frame(kind: str) -> dict[str, Any]:
    line = (SAMPLES / f"format_{kind}.jsonl").read_text().splitlines()[0]
    return decode(json.loads(line)["frame"])


@pytest.fixture(scope="module")
def frames() -> list[dict[str, Any]]:
    visits = synth.plan_visits(PRIORS, WINDOW_END, seed=7, closures=[])
    rows: list[dict[str, Any]] = []
    for h in range(6):
        hour = WINDOW_END - timedelta(hours=6 - h)
        rows += synth.frames_for_hour(visits, hour, PRIORS, seed=7, scenario="test")
    return rows


@pytest.mark.parametrize(
    ("kind", "message_type"),
    [
        ("position_report", "PositionReport"),
        ("ship_static_data", "ShipStaticData"),
    ],
)
def test_synthetic_frames_match_real_shape(
    frames: list[dict[str, Any]], kind: str, message_type: str
) -> None:
    real = real_frame(kind)
    fake = next(
        decode(r["frame"]) for r in frames if decode(r["frame"])["MessageType"] == message_type
    )
    assert shape(fake) == shape(real)


def test_envelope_labels_synthetic(frames: list[dict[str, Any]]) -> None:
    assert frames, "six hours should contain frames"
    for row in frames[:50]:
        assert row["is_synthetic"] is True and row["scenario_id"] == "test"
        mmsi = decode(row["frame"])["MetaData"]["MMSI"]
        assert str(mmsi).startswith(str(synth.MID))  # never collides with a real vessel
    times = [r["received_at"] for r in frames]
    assert times == sorted(times)


def test_positions_parse_like_real_ones(frames: list[dict[str, Any]]) -> None:
    parsed = [position(decode(r["frame"])) for r in frames]
    assert all(p is not None for p in parsed)


def test_deterministic_for_a_seed() -> None:
    a = synth.plan_visits(PRIORS, WINDOW_END, seed=3, closures=[])
    b = synth.plan_visits(PRIORS, WINDOW_END, seed=3, closures=[])
    assert [synth.ground_truth(v, "s") for v in a] == [synth.ground_truth(v, "s") for v in b]


def test_ground_truth_invariants() -> None:
    for visit in synth.plan_visits(PRIORS, WINDOW_END, seed=11, closures=[]):
        truth = synth.ground_truth(visit, "s")
        assert truth["anchorage_wait_h"] >= 0 and truth["berth_h"] >= 0
        assert truth["vessel_dwell_h"] == pytest.approx(
            truth["anchorage_wait_h"] + truth["berth_h"], abs=0.02
        )
        if truth["berth_start"]:
            assert truth["berth_start"] >= truth["arrive_anchorage"]


def test_closure_delays_river_transits() -> None:
    closure = (WINDOW_END - timedelta(days=3), WINDOW_END - timedelta(days=1))
    for visit in synth.plan_visits(PRIORS, WINDOW_END, seed=5, closures=[closure]):
        start = visit.truth.get("berth_start")
        leave = visit.truth["leave_anchorage"]
        if start is not None:
            assert not closure[0] <= leave < closure[1]
