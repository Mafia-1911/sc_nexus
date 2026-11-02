"""BD-bound ships from free-text AIS destinations (DS-AIS-01, U-07)."""

from __future__ import annotations

from datetime import UTC, datetime

from cportal_connectors.ais_bd_bound import eta, port_of


def test_destination_spellings_map_to_bangladesh_ports() -> None:
    for text in ("BDCGP", "BD CGP", "CHITTAGONG", "CHITAGONG BD", "CTG BD", "SGSIN>BDCGP"):
        assert port_of(text) == "BDCGP", text
    assert port_of("MONGLA") == "BDMGL" and port_of("BD MGL") == "BDMGL"
    assert port_of("PAYRA") == "BDPAY"
    for text in ("SGSIN", "CN HKG > CN SKU", "BDX TANK", "OCTOBER", ""):
        assert port_of(text) is None, text


def test_ais_eta_has_no_year_and_rolls_into_next_year() -> None:
    seen = datetime(2026, 12, 28, tzinfo=UTC)
    assert eta({"Month": 1, "Day": 4, "Hour": 6, "Minute": 30}, seen) == "2027-01-04T06:30:00+00:00"
    assert (
        eta({"Month": 12, "Day": 30, "Hour": 24, "Minute": 60}, seen) == "2026-12-30T00:00:00+00:00"
    )
    assert eta({"Month": 0, "Day": 0}, seen) is None
