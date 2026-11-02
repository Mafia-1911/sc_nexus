"""Route Planner traffic (A-106): Bangladesh-only tile proxy, C3's modelled zones."""

from __future__ import annotations

from cportal_api.routers.traffic import _in_bangladesh, modelled


def test_tiles_are_served_for_bangladesh_only() -> None:
    assert _in_bangladesh(12, 3076, 1770)  # Dhaka
    assert not _in_bangladesh(12, 0, 0)
    assert not _in_bangladesh(8, 128, 85)  # London


def test_modelled_zones_follow_the_hour_profile_and_the_ban() -> None:
    rush = modelled(hour=17).data
    night = modelled(hour=2).data
    zone = {f["properties"]["zone"]: f["properties"] for f in rush["geojson"]["features"]}
    assert zone["dhaka"]["factor"] < 0.6 and zone["truck_ban"]["active"] is True
    night_zone = {f["properties"]["zone"]: f["properties"] for f in night["geojson"]["features"]}
    assert night_zone["dhaka"]["factor"] == 1.0 and night_zone["truck_ban"]["active"] is False
    assert "estimates" in rush["source"]
