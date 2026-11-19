"""C6 change detection between two snapshots of one schedule scope."""

from __future__ import annotations

import datetime as dt
from typing import Any

from cportal_c6.diff import diff_measures
from cportal_c6.rates import Measure


def m(ref: str, pct: float | None, h: str, **kw: Any) -> Measure:
    base: dict[str, Any] = {
        "id": f"{ref}-{h}",
        "market": "USA",
        "code": "*",
        "hs6": None,
        "kind": "additional",
        "origin_kind": "country",
        "origin_code": "BGD",
        "duty_text": f"+ {pct}%",
        "ad_valorem_pct": pct,
        "is_resolved": True,
        "measure_ref": ref,
        "legal_ref": None,
        "source_id": "DS-TRADE-05",
        "status": "in_force",
        "valid_from": None,
        "valid_to": None,
        "conditions": {},
        "content_hash": h,
    }
    base.update(kw)
    return Measure(**base)


def test_no_change() -> None:
    a = [m("9903.05.26", 10.0, "h1")]
    assert diff_measures(a, a) == []


def test_rate_change_is_one_changed_row_with_delta() -> None:
    (c,) = diff_measures(
        [m("9903.05.26", 10.0, "h1")],
        [m("9903.05.26", 15.0, "h2", valid_from=dt.date(2026, 12, 1))],
    )
    assert c.change == "changed" and c.delta_pp == 5.0
    assert (c.old.ad_valorem_pct, c.new.ad_valorem_pct) == (10.0, 15.0)
    assert c.effective_from == dt.date(2026, 12, 1)


def test_added_and_removed() -> None:
    changes = diff_measures([m("9903.01.66", 37.0, "a")], [m("9903.05.26", 10.0, "b")])
    assert sorted((c.change, (c.new or c.old).measure_ref) for c in changes) == [
        ("added", "9903.05.26"),
        ("removed", "9903.01.66"),
    ]
    added = next(c for c in changes if c.change == "added")
    assert added.delta_pp == 10.0 and added.old is None


def test_termination_is_a_change_without_rate_delta() -> None:
    (c,) = diff_measures(
        [m("9903.01.66", 37.0, "a")], [m("9903.01.66", 37.0, "b", status="terminated")]
    )
    assert c.change == "changed" and c.delta_pp == -37.0
    assert (c.old.status, c.new.status) == ("in_force", "terminated")


def test_same_rule_for_different_origins_is_not_confused() -> None:
    old = [m("9903.05.26", 10.0, "a"), m("9903.05.26", 12.5, "b", origin_code="VNM")]
    new = [m("9903.05.26", 10.0, "a"), m("9903.05.26", 20.0, "c", origin_code="VNM")]
    (c,) = diff_measures(old, new)
    assert c.new.origin_code == "VNM" and c.delta_pp == 7.5


def test_output_is_ordered_and_deterministic() -> None:
    old = [m(f"9903.05.{i:02d}", 1.0, f"o{i}") for i in range(5)]
    new = [m(f"9903.05.{i:02d}", 2.0, f"n{i}") for i in reversed(range(5))]
    refs = [c.new.measure_ref for c in diff_measures(old, new)]
    assert refs == sorted(refs)


# Review 2026-11-19 #2: a preference replaces the base, so adding one is a cut, not +pct.
def _pref(pct: float, h: str) -> Measure:
    return m("GBR-1062", pct, h, kind="preferential", origin_kind="group", origin_code="1062")


def test_added_preference_has_no_delta_and_reads_as_a_cut() -> None:
    from cportal_c6.diff import direction

    (c,) = diff_measures([], [_pref(5.0, "p1")])
    assert c.change == "added" and c.delta_pp is None
    assert direction("preferential", "1062", c.change, c.delta_pp) == "cut"


def test_removed_free_preference_reads_as_a_raise() -> None:
    from cportal_c6.diff import direction

    (c,) = diff_measures([_pref(0.0, "p1")], [])
    assert c.delta_pp is None
    assert direction("preferential", "1062", c.change, c.delta_pp) == "raise"


def test_changed_preference_rate_keeps_its_delta() -> None:
    (c,) = diff_measures([_pref(5.0, "p1")], [_pref(2.0, "p2")])
    assert c.delta_pp == -3.0


def test_quota_change_has_no_delta() -> None:
    (c,) = diff_measures([], [m("q1", 3.0, "q", kind="quota")])
    assert c.delta_pp is None
