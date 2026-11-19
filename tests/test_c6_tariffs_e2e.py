"""C6 end to end on a real Postgres: the real probed samples → loader → C6 refresh.

The expected duties are the official ones in the samples (USITC HTS, UK Trade Tariff, WITS),
plus the hand-kept EU table. A planted rate change in a later snapshot must be detected once,
re-key the measure, and move the effective rate; a second refresh must find nothing new.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator

import pytest
from cportal_c6 import store
from cportal_connectors.canonical import ParseContext, sample_bytes
from cportal_connectors.parsers.tariffs import hts_parser
from cportal_connectors.registry import connectors
from cportal_core.db import session_scope
from cportal_core.enums import DataMode
from cportal_core.loader import upsert
from cportal_core.models import (
    OutboxEvent,
    TariffChange,
    TariffEffectiveRate,
    TariffMeasure,
)
from cportal_core.testing import TEST_URL, database_available, reset_database
from sqlalchemy import func, select

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")

ON = dt.date(2026, 11, 18)
TARIFF_SOURCES = ("DS-TRADE-04", "DS-TRADE-05", "DS-TRADE-06", "DS-TRADE-07", "DS-TRADE-08")


@pytest.fixture(scope="module")
def loaded() -> Iterator[str]:
    reset_database()
    with session_scope(TEST_URL) as s:
        for ds in TARIFF_SOURCES:
            upsert(s, connectors()[ds].replay())
    with session_scope(TEST_URL) as s:
        store.refresh(s, ON)
    yield TEST_URL


def _rate(url: str, market: str, hs6: str, origin: str) -> TariffEffectiveRate:
    with session_scope(url) as s:
        row = s.scalar(
            select(TariffEffectiveRate).where(
                TariffEffectiveRate.as_of == ON,
                TariffEffectiveRate.market_iso3 == market,
                TariffEffectiveRate.hs6 == hs6,
                TariffEffectiveRate.origin_iso3 == origin,
            )
        )
        assert row is not None, (market, hs6, origin)
        s.expunge(row)
        return row


@pytest.mark.parametrize(
    ("origin", "expected"),
    [("BGD", 26.5), ("KHM", 26.5), ("IND", 26.5), ("VNM", 29.0)],
)
def test_us_cotton_tshirt_mfn_plus_country_surcharge(
    loaded: str, origin: str, expected: float
) -> None:
    r = _rate(loaded, "USA", "610910", origin)
    assert r.effective_pct_max == pytest.approx(expected) and r.is_resolved
    assert r.base_pct == 16.5 and r.n_lines == 1
    assert r.sources == ["DS-TRADE-05"]  # the live schedule, not the WITS average


def test_us_china_has_several_surcharges_and_no_guessed_total(loaded: str) -> None:
    r = _rate(loaded, "USA", "610910", "CHN")
    assert r.is_resolved is False and r.effective_pct_max is None and r.base_pct == 16.5
    refs = {c["measure_ref"] for c in r.components if c["role"] == "additional"}
    assert {"9903.01.20", "9903.01.24", "9903.01.63", "9903.05.31"} <= refs
    assert any("if they all stack" in n for n in r.notes)


def test_us_medicaments_surcharge_may_not_apply(loaded: str) -> None:
    # 9903.05.89 exempts "articles for use in pharmaceutical applications" (U.S. note 52(e)):
    # the HS list is in the note, so the cell says so instead of adding the 10 %
    r = _rate(loaded, "USA", "300490", "BGD")
    assert r.is_resolved is False and r.effective_pct_max is None
    assert any("9903.05.89" in n and "pharmaceutical" in n for n in r.notes)


def test_us_bangladesh_lists_the_possible_exemption(loaded: str) -> None:
    roles = {
        (c["role"], c["measure_ref"]) for c in _rate(loaded, "USA", "610910", "BGD").components
    }
    assert ("additional", "9903.05.26") in roles
    assert ("possible_exemption", "9903.06.12") in roles
    # terminated and expired surcharges are not in the bill
    assert not any(ref in {"9903.01.66", "9903.02.05"} for _, ref in roles)


@pytest.mark.parametrize(
    ("origin", "expected"),
    [("BGD", 0.0), ("VNM", 0.0), ("IND", 0.0), ("CHN", 12.0)],
)
def test_uk_cotton_tshirt(loaded: str, origin: str, expected: float) -> None:
    r = _rate(loaded, "GBR", "610910", origin)
    assert r.effective_pct_min == pytest.approx(expected) and r.is_resolved
    assert r.base_pct == 12.0


def test_uk_bangladesh_preference_is_dcts_comprehensive(loaded: str) -> None:
    (pref,) = [
        c for c in _rate(loaded, "GBR", "610910", "BGD").components if c["role"] == "preference"
    ]
    assert pref["origin_code"] == "1062" and pref["source_id"] == "DS-TRADE-07"


@pytest.mark.parametrize(
    ("origin", "expected", "resolved"),
    [
        ("BGD", 0.0, True),
        ("PAK", 0.0, True),
        ("LKA", 0.0, True),
        ("IND", 12.0, True),
        ("CHN", 12.0, True),
        ("VNM", None, False),
    ],
)
def test_eu_cotton_tshirt(loaded: str, origin: str, expected: float | None, resolved: bool) -> None:
    r = _rate(loaded, "EUN", "610910", origin)
    assert r.is_resolved is resolved
    if expected is None:
        assert r.effective_pct_max is None and r.base_pct == 12.0
    else:
        assert r.effective_pct_max == pytest.approx(expected)
    assert set(r.sources) <= {"DS-TRADE-04", "DS-TRADE-08"}
    assert r.is_stale  # EU MFN comes from WITS 2023


def test_markets_without_preference_data_give_a_ceiling(loaded: str) -> None:
    """Japan and Canada: WITS MFN only, no preference data (e.g. LDC duty-free access), so the
    number is the most a Bangladeshi good pays, not what it pays."""
    for market in ("JPN", "CAN"):
        assert _rate(loaded, market, "610910", "BGD").is_ceiling is True
    for market in ("USA", "GBR", "EUN"):
        assert _rate(loaded, market, "610910", "BGD").is_ceiling is False
    assert any("may be lower" in n for n in _rate(loaded, "CAN", "610910", "BGD").notes)


def test_every_cell_is_written_and_badged(loaded: str) -> None:
    with session_scope(loaded) as s:
        n = s.scalar(select(func.count()).select_from(TariffEffectiveRate))
        modes = set(s.scalars(select(TariffEffectiveRate.data_mode).distinct()))
    assert n == 5 * 22 * 7  # markets × watched HS6 × origins
    assert modes == {"replay"}


def test_change_detection_end_to_end(loaded: str) -> None:
    name = "hts_export_9903_01_07.json"
    rows = json.loads(sample_bytes("DS-TRADE-05", name))
    (target,) = [r for r in rows if r["htsno"] == "9903.05.26"]  # Bangladesh, note 52
    assert target["general"].endswith("+ 10%")
    target["general"] = "The duty provided in the applicable subheading + 15%"
    planted = json.dumps(rows).encode()
    later = ParseContext(
        "DS-TRADE-05", DataMode.LIVE, fetched_at=dt.datetime(2026, 11, 19, 6, tzinfo=dt.UTC)
    )
    with session_scope(loaded) as s:
        upsert(s, hts_parser("hts:9903.01-9903.07")(planted, later))
        summary = store.refresh(s, ON)
    assert summary["new_changes"] == 1
    with session_scope(loaded) as s:
        (c,) = s.scalars(select(TariffChange)).all()
        assert (c.measure_ref, c.origin_code, c.change) == ("9903.05.26", "BGD", "changed")
        assert (c.old_ad_valorem_pct, c.new_ad_valorem_pct, c.delta_pp) == (10.0, 15.0, 5.0)
        assert c.data_mode == "live"
        old = s.get(TariffMeasure, c.old_measure_id)
        new = s.get(TariffMeasure, c.new_measure_id)
        assert old is not None and new is not None
        assert old.is_current is False and new.is_current is True
        topics = list(s.scalars(select(OutboxEvent.topic)))
        assert topics.count("tariff.changed") == 1
    r = _rate(loaded, "USA", "610910", "BGD")
    assert r.effective_pct_max == pytest.approx(31.5) and r.data_mode == "live"
    assert _rate(loaded, "USA", "610910", "VNM").effective_pct_max == pytest.approx(29.0)
    with session_scope(loaded) as s:  # idempotent: nothing new the second time
        assert store.refresh(s, ON)["new_changes"] == 0


def test_a_parser_upgrade_is_not_a_tariff_change(
    loaded: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new parser version may read more rules from the same schedule; that must re-baseline,
    not show up as tariff changes."""
    from cportal_connectors.parsers import tariffs as T

    rows = json.loads(sample_bytes("DS-TRADE-05", "hts_export_9903_01_07.json"))
    rows = [r for r in rows if r["htsno"] != "9903.05.89"]  # as if the old parser missed it
    later = ParseContext(
        "DS-TRADE-05", DataMode.LIVE, fetched_at=dt.datetime(2026, 11, 20, 6, tzinfo=dt.UTC)
    )
    monkeypatch.setattr(T, "PARSER_VERSION", T.PARSER_VERSION + "-old")
    with session_scope(loaded) as s:
        upsert(s, hts_parser("hts:9903.01-9903.07")(json.dumps(rows).encode(), later))
        s.flush()
        before = s.scalar(select(func.count()).select_from(TariffChange))
        assert store.refresh(s, ON)["new_changes"] == 0
        assert s.scalar(select(func.count()).select_from(TariffChange)) == before


def test_unversioned_snapshots_are_never_diffed(loaded: str) -> None:
    """Snapshots written before parser versioning cannot be compared safely (their parser may
    have read the schedule differently): they re-baseline instead of producing changes."""
    rows = json.loads(sample_bytes("DS-TRADE-05", "hts_export_9903_01_07.json"))
    rows = [r for r in rows if r["htsno"] != "9903.05.90"]
    recs = []
    for when in (dt.datetime(2026, 12, 1, tzinfo=dt.UTC), dt.datetime(2026, 12, 2, tzinfo=dt.UTC)):
        ctx = ParseContext("DS-TRADE-05", DataMode.LIVE, fetched_at=when)
        body = json.dumps(
            rows
            if when.day == 1
            else json.loads(sample_bytes("DS-TRADE-05", "hts_export_9903_01_07.json"))
        ).encode()
        out = hts_parser("hts:9903.01-9903.07")(body, ctx)
        for r in out:
            if r.table == "tariff_snapshot":
                r.generator_version = None  # as written before versioning
        recs += out
    with session_scope(loaded) as s:
        upsert(s, recs)
        s.flush()
        assert store.refresh(s, ON)["new_changes"] == 0


def test_bounds_are_consistent_and_china_gets_a_stacked_range(loaded: str) -> None:
    """Review 2026-11-19 #1: unresolved cells carry what is known, never MFN as a floor."""
    with session_scope(loaded) as s:
        rows = list(s.scalars(select(TariffEffectiveRate).where(TariffEffectiveRate.as_of == ON)))
    assert rows
    for r in rows:
        if r.is_resolved:
            assert r.lower_pct == pytest.approx(r.effective_pct_min)
            assert r.upper_pct == pytest.approx(r.effective_pct_max)
        elif r.lower_pct is not None and r.upper_pct is not None:
            assert r.lower_pct <= r.upper_pct
    china = _rate(loaded, "USA", "610910", "CHN")
    assert not china.is_resolved
    assert china.lower_pct is not None and china.lower_pct > china.base_pct


def test_an_empty_response_is_not_a_mass_removal(loaded: str) -> None:
    """Review 2026-11-19 #5: a 200 with no rows (a flaky fetch) must not mark the whole scope
    non-current or record every rule as removed."""
    later = ParseContext(
        "DS-TRADE-05", DataMode.LIVE, fetched_at=dt.datetime(2026, 12, 10, 6, tzinfo=dt.UTC)
    )
    with session_scope(loaded) as s:
        before = s.scalar(select(func.count()).select_from(TariffChange))
        current = s.scalar(
            select(func.count()).select_from(TariffMeasure).where(TariffMeasure.is_current)
        )
        upsert(s, hts_parser("hts:9903.01-9903.07")(b"[]", later))
        s.flush()
        assert store.refresh(s, ON)["new_changes"] == 0
        assert s.scalar(select(func.count()).select_from(TariffChange)) == before
        assert (
            s.scalar(
                select(func.count()).select_from(TariffMeasure).where(TariffMeasure.is_current)
            )
            == current
        )


def test_an_edit_to_the_eu_table_without_a_new_date_is_detected(loaded: str) -> None:
    """Review 2026-11-19 #6: the hand-kept table is versioned by its content."""
    import yaml
    from cportal_connectors.parsers.tariffs import parse_eu_preferences
    from cportal_core.paths import config_dir

    doc = yaml.safe_load((config_dir() / "tariffs" / "eu_preferences.yaml").read_text())
    doc["groups"]["EU-EBA"]["measures"][0].update(ad_valorem_pct=2, duty_text="2%")
    with session_scope(loaded) as s:
        upsert(s, parse_eu_preferences(yaml.safe_dump(doc).encode(),
                                       ParseContext("DS-TRADE-08", DataMode.REPLAY)))  # fmt: skip
        s.flush()
        assert store.refresh(s, ON)["new_changes"] == 1
        (c,) = s.scalars(select(TariffChange).where(TariffChange.origin_code == "EU-EBA")).all()
        assert (c.change, c.delta_pp) == ("changed", 2.0)
    assert _rate(loaded, "EUN", "610910", "BGD").effective_pct_max == pytest.approx(2.0)
