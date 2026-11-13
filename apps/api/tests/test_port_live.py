"""CPA visit classification for the live map, KPIs and Ships table (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cportal_api.routers.port_live import classify
from cportal_core.models import PortCall

NOW = datetime(2026, 11, 13, 10, tzinfo=UTC)


def _call(phase: str, ata_days: float | None, **attrs: object) -> PortCall:
    ata = NOW - timedelta(days=ata_days) if ata_days is not None else None
    return PortCall(phase=phase, arrival_ts=ata, attrs=dict(attrs))


def test_anchorage_visits_cpa_never_closed_are_stale() -> None:
    """A-116: a break-bulk ship 'WORKING' at the anchorage since 2018 is not at the anchorage."""
    assert classify(_call("WORKING", 9, cargo="breakbulk"), NOW) == "at_anchorage"
    assert classify(_call("ARRIVED", 2), NOW) == "at_anchorage"
    assert classify(_call("WORKING", 2970, cargo="breakbulk"), NOW) is None
    assert classify(_call("ARRIVED", 45), NOW) is None


def test_berth_reports_beat_the_schedule_phase() -> None:
    at_berth = _call("WORKING", 400, berth="NCT-2")
    at_berth.berth_start_ts = NOW - timedelta(hours=20)
    assert classify(at_berth, NOW) == "at_berth"  # a berth report is current, whatever the ATA
