"""Which schedule change confirms a tariff news story (review 2026-11-19 #7)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from cportal_c6.service import _confirmation
from cportal_core.models import TariffChange

PUBLISHED = dt.datetime(2026, 11, 10, tzinfo=dt.UTC)
GARMENT_STORY = {
    "markets": ["USA"],
    "origins": ["BGD"],
    "direction": "raise",
    "industries": ["garments"],
}


def change(**kw: Any) -> TariffChange:
    base: dict[str, Any] = {
        "market_iso3": "USA",
        "code": "*",
        "hs6": None,
        "kind": "additional",
        "origin_code": "BGD",
        "change": "changed",
        "delta_pp": 5.0,
        "detected_at": PUBLISHED + dt.timedelta(days=3),
        "measure_ref": "9903.05.26",
    }
    base.update(kw)
    return TariffChange(**base)


def test_a_country_wide_raise_confirms_the_story() -> None:
    c = change()
    assert _confirmation([c], GARMENT_STORY, PUBLISHED) is c


def test_a_change_on_another_industrys_product_does_not_confirm() -> None:
    pharma = change(code="30049092", hs6="300490", kind="mfn", origin_code="*")
    assert _confirmation([pharma], GARMENT_STORY, PUBLISHED) is None
    tshirt = change(code="61091000", hs6="610910", kind="mfn", origin_code="*")
    assert _confirmation([tshirt], GARMENT_STORY, PUBLISHED) is tshirt


def test_a_group_change_confirms_a_story_about_a_member() -> None:
    removed = change(kind="preferential", origin_code="US-SP-A", change="removed", delta_pp=None)
    members = {("USA", "US-SP-A"): [("BGD", None, None)]}
    assert _confirmation([removed], GARMENT_STORY, PUBLISHED, members) is removed
    assert _confirmation([removed], GARMENT_STORY, PUBLISHED, {}) is None


def test_an_added_preference_is_a_cut_not_a_raise() -> None:
    added = change(kind="preferential", origin_code="BGD", change="added", delta_pp=None)
    assert _confirmation([added], GARMENT_STORY, PUBLISHED) is None
    assert _confirmation([added], {**GARMENT_STORY, "direction": "cut"}, PUBLISHED) is added
