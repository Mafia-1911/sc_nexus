"""C6 effective-rate engine: one rule per test, on hand-built measures."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from cportal_c6.rates import Measure, Membership, effective_rate

ON = dt.date(2026, 11, 18)


def m(**kw: Any) -> Measure:
    base: dict[str, Any] = {
        "id": kw.get("measure_ref", "x"),
        "market": "USA",
        "code": "61091000",
        "hs6": "610910",
        "kind": "mfn",
        "origin_kind": "erga_omnes",
        "origin_code": "*",
        "duty_text": "",
        "ad_valorem_pct": None,
        "is_resolved": True,
        "measure_ref": "6109.10.00",
        "legal_ref": None,
        "source_id": "DS-TRADE-05",
        "status": "in_force",
        "valid_from": None,
        "valid_to": None,
        "conditions": {},
    }
    base.update(kw)
    return Measure(**base)


MFN = m(ad_valorem_pct=16.5, duty_text="16.5%")
MEMBERS: Membership = {
    ("USA", "US-SP-S"): [("CAN", None, None), ("MEX", None, None)],
    ("USA", "US-COL2"): [("RUS", None, None)],
    ("GBR", "1062"): [("BGD", None, None)],
    ("EUN", "EU-EBA"): [("BGD", None, dt.date(2029, 11, 24))],
    ("EUN", "EU-GSP"): [("IND", None, None)],
}


def test_mfn_only() -> None:
    r = effective_rate([MFN], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 16.5 and r.is_resolved
    assert [c.role for c in r.components] == ["base"]


def test_country_surcharge_adds_to_base() -> None:
    surcharge = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=10.0,
        measure_ref="9903.05.26",
    )
    r = effective_rate([MFN, surcharge], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 26.5 and r.additional_pct == 10.0 and r.base_pct == 16.5
    other = effective_rate([MFN, surcharge], MEMBERS, "USA", "61091000", "VNM", ON)
    assert other.effective_pct == 16.5  # someone else's surcharge does not apply


def test_terminated_and_expired_surcharges_do_not_apply() -> None:
    old = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=37.0,
        status="terminated",
        measure_ref="9903.01.66",
    )
    window = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=20.0,
        valid_from=dt.date(2025, 8, 7),
        valid_to=dt.date(2025, 10, 4),
        measure_ref="9903.02.05",
    )
    assert (
        effective_rate([MFN, old, window], MEMBERS, "USA", "61091000", "BGD", ON).effective_pct
        == 16.5
    )
    # on a date inside the window, the 20 % applied
    then = effective_rate([MFN, window], MEMBERS, "USA", "61091000", "BGD", dt.date(2025, 9, 1))
    assert then.effective_pct == 36.5


def test_group_preference_replaces_base_for_members_only() -> None:
    usmca = m(kind="preferential", origin_kind="group", origin_code="US-SP-S", ad_valorem_pct=0.0)
    assert effective_rate([MFN, usmca], MEMBERS, "USA", "61091000", "MEX", ON).effective_pct == 0.0
    r = effective_rate([MFN, usmca], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 16.5 and r.preference_pct is None


def test_best_preference_wins_and_notes_rules_of_origin() -> None:
    a = m(
        kind="preferential",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=5.0,
        measure_ref="a",
    )
    b = m(
        kind="preferential",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=2.0,
        measure_ref="b",
    )
    r = effective_rate([MFN, a, b], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 2.0 and r.preference_pct == 2.0
    assert any("rules of origin" in n for n in r.notes)


def test_partial_eligibility_is_not_applied_automatically() -> None:
    e = m(
        kind="preferential",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=0.0,
        conditions={"partial_eligibility": True},
    )
    r = effective_rate([MFN, e], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 16.5
    assert any(c.role == "not_applied" for c in r.components)


def test_column2_replaces_mfn() -> None:
    col2 = m(kind="column2", origin_kind="group", origin_code="US-COL2", ad_valorem_pct=90.0)
    assert effective_rate([MFN, col2], MEMBERS, "USA", "61091000", "RUS", ON).effective_pct == 90.0
    assert effective_rate([MFN, col2], MEMBERS, "USA", "61091000", "BGD", ON).effective_pct == 16.5


def test_membership_end_date_is_respected() -> None:
    mfn = m(market="EUN", code="610910", ad_valorem_pct=12.0, source_id="DS-TRADE-04")
    eba = m(
        market="EUN",
        code="*",
        hs6=None,
        kind="preferential",
        origin_kind="group",
        origin_code="EU-EBA",
        ad_valorem_pct=0.0,
        conditions={"exclude_chapters": ["93"]},
    )
    assert effective_rate([mfn, eba], MEMBERS, "EUN", "610910", "BGD", ON).effective_pct == 0.0
    after = effective_rate([mfn, eba], MEMBERS, "EUN", "610910", "BGD", dt.date(2029, 12, 1))
    assert after.effective_pct == 12.0


def test_chapter_filters() -> None:
    mfn = m(market="EUN", code="930100", hs6="930100", ad_valorem_pct=3.2)
    eba = m(
        market="EUN",
        code="*",
        hs6=None,
        kind="preferential",
        origin_kind="group",
        origin_code="EU-EBA",
        ad_valorem_pct=0.0,
        conditions={"exclude_chapters": ["93"]},
    )
    assert effective_rate([mfn, eba], MEMBERS, "EUN", "930100", "BGD", ON).effective_pct == 3.2


def test_relative_preference_is_computed_from_base() -> None:
    mfn = m(market="EUN", code="610910", ad_valorem_pct=12.0)
    gsp = m(
        market="EUN",
        code="*",
        hs6=None,
        kind="preferential",
        origin_kind="group",
        origin_code="EU-GSP",
        ad_valorem_pct=None,
        is_resolved=False,
        conditions={"mfn_reduction_pct": 20, "include_chapters": ["61", "62", "63"]},
    )
    r = effective_rate([mfn, gsp], MEMBERS, "EUN", "610910", "IND", ON)
    assert r.effective_pct == pytest.approx(9.6) and r.is_resolved
    pharma = m(market="EUN", code="300490", hs6="300490", ad_valorem_pct=0.0)
    assert effective_rate([pharma, gsp], MEMBERS, "EUN", "300490", "IND", ON).preference_pct is None


def test_unresolved_preference_makes_the_result_unresolved_not_a_guess() -> None:
    mfn = m(market="EUN", code="610910", ad_valorem_pct=12.0)
    fta = m(
        market="EUN",
        code="*",
        hs6=None,
        kind="preferential",
        origin_kind="country",
        origin_code="VNM",
        ad_valorem_pct=None,
        is_resolved=False,
        duty_text="Staged reduction: see legal text",
    )
    r = effective_rate([mfn, fta], MEMBERS, "EUN", "610910", "VNM", ON)
    assert r.is_resolved is False and r.effective_pct is None
    assert r.base_pct == 12.0  # the ceiling is still known


def test_specific_duty_is_unresolved() -> None:
    spec = m(ad_valorem_pct=None, is_resolved=False, duty_text="3.4¢/kg")
    r = effective_rate([spec], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct is None and not r.is_resolved


def test_exemptions_and_remedies_are_notes_not_numbers() -> None:
    surcharge = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=10.0,
        measure_ref="9903.05.26",
    )
    ex = m(
        code="*",
        hs6=None,
        kind="exemption",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=0.0,
        is_resolved=False,
        measure_ref="9903.06.12",
    )
    r = effective_rate([MFN, surcharge, ex], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct == 26.5
    assert any(
        c.role == "possible_exemption" and c.measure_ref == "9903.06.12" for c in r.components
    )


def test_most_specific_code_wins_for_base() -> None:
    heading = m(code="6109", hs6=None, ad_valorem_pct=20.0, measure_ref="h")
    line = m(code="61091000", ad_valorem_pct=16.5, measure_ref="l")
    assert effective_rate([heading, line], MEMBERS, "USA", "61091000", "BGD", ON).base_pct == 16.5


def test_stale_annual_rate_is_used_and_flagged() -> None:
    wits = m(
        market="JPN",
        code="610910",
        ad_valorem_pct=10.9,
        valid_from=dt.date(2023, 1, 1),
        valid_to=dt.date(2023, 12, 31),
        source_id="DS-TRADE-04",
    )
    r = effective_rate([wits], MEMBERS, "JPN", "610910", "BGD", ON)
    assert r.effective_pct == 10.9 and r.is_stale
    assert any("2023" in n for n in r.notes)


def test_no_base_rate() -> None:
    r = effective_rate([], MEMBERS, "USA", "61091000", "BGD", ON)
    assert r.effective_pct is None and not r.is_resolved
    assert any("no MFN" in n for n in r.notes)


def test_other_markets_measures_are_ignored() -> None:
    uk = m(market="GBR", code="61091000", ad_valorem_pct=12.0)
    assert effective_rate([MFN, uk], MEMBERS, "USA", "61091000", "BGD", ON).effective_pct == 16.5


def test_several_surcharges_for_one_origin_are_unresolved_not_summed() -> None:
    # the HTS text alone does not say whether IEEPA lines stack or supersede each other
    a = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="CHN",
        ad_valorem_pct=10.0,
        measure_ref="9903.01.20",
    )
    b = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="CHN",
        ad_valorem_pct=12.5,
        measure_ref="9903.05.31",
    )
    r = effective_rate([MFN, a, b], MEMBERS, "USA", "61091000", "CHN", ON)
    assert r.effective_pct is None and r.is_resolved is False
    assert r.base_pct == 16.5 and r.additional_pct == 22.5
    assert {c.measure_ref for c in r.components if c.role == "additional"} == {
        "9903.01.20",
        "9903.05.31",
    }
    assert any("39" in n for n in r.notes)  # 16.5 + 10 + 12.5 if they all stack


def test_average_of_differing_lines_is_unresolved_but_says_the_range() -> None:
    wits = m(
        market="JPN",
        code="610910",
        ad_valorem_pct=9.1,
        is_resolved=False,
        duty_text="9.1% (simple average of 2 national lines)",
        source_id="DS-TRADE-04",
        conditions={"simple_average_of_lines": 2, "min_rate": "7.4", "max_rate": "10.9"},
    )
    r = effective_rate([wits], MEMBERS, "JPN", "610910", "BGD", ON)
    assert r.effective_pct is None and r.base_pct is None
    assert any("7.4" in n and "10.9" in n and "2 national lines" in n for n in r.notes)


def test_category_exemption_makes_a_matching_surcharge_unresolved() -> None:
    pharma_mfn = m(code="30049092", hs6="300490", ad_valorem_pct=0.0, duty_text="Free")
    surcharge = m(
        code="*",
        hs6=None,
        kind="additional",
        origin_kind="country",
        origin_code="BGD",
        ad_valorem_pct=10.0,
        measure_ref="9903.05.26",
    )
    exemption = m(
        code="*",
        hs6=None,
        kind="exemption",
        origin_kind="erga_omnes",
        origin_code="*",
        ad_valorem_pct=0.0,
        is_resolved=False,
        measure_ref="9903.05.89",
        conditions={"include_chapters": ["29", "30"], "category": "pharmaceutical applications"},
    )
    r = effective_rate([pharma_mfn, surcharge, exemption], MEMBERS, "USA", "30049092", "BGD", ON)
    assert r.effective_pct is None and r.is_resolved is False and r.base_pct == 0.0
    assert any("pharmaceutical applications" in n and "9903.05.89" in n for n in r.notes)
    # a T-shirt is outside the category's chapters: the surcharge stands
    tee = effective_rate([MFN, surcharge, exemption], MEMBERS, "USA", "61091000", "BGD", ON)
    assert tee.effective_pct == 26.5 and tee.is_resolved
