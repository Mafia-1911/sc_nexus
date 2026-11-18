"""C6 tariff parsers (ADR-021) on the real samples probed 2026-11-18 (D-08).

Every expected number below was read off the official source in the committed sample, so a
parser change that misreads a rate, an origin, a date or a product code fails here.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest
from cportal_connectors.canonical import ParseContext, sample_bytes, sample_fetched_at
from cportal_connectors.parsers import tariffs as T
from cportal_core.enums import DataMode
from cportal_core.schemas.records import (
    TariffMeasureRecord,
    TariffNomenclatureRecord,
    TariffOriginGroupRecord,
    TariffOriginMemberRecord,
    TariffSnapshotRecord,
    TradePolicyNoticeRecord,
)


def _ctx(ds_id: str, name: str) -> ParseContext:
    return ParseContext(ds_id, DataMode.REPLAY, fetched_at=sample_fetched_at(ds_id, name))


def _of(records: list, kind: type) -> list:
    return [r for r in records if isinstance(r, kind)]


# --- duty text ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "pct", "specific", "unit", "compound", "resolved", "additive"),
    [
        ("16.5%", 16.5, None, None, False, True, False),
        ("Free", 0.0, None, None, False, True, False),
        ("12.00 %", 12.0, None, None, False, True, False),
        ("9.60 %", 9.6, None, None, False, True, False),
        ("3.4¢/kg", None, 3.4, "¢/kg", False, False, False),
        ("2.4¢/kg + 10%", 10.0, 2.4, "¢/kg", True, False, False),
        (
            "The duty provided in the applicable subheading + 10%",
            10.0,
            None,
            None,
            False,
            True,
            True,
        ),
        (
            "The duty provided in the applicable subheading + 12.5%",
            12.5,
            None,
            None,
            False,
            True,
            True,
        ),
        ("The duty provided in the applicable subheading", 0.0, None, None, False, True, True),
    ],
)
def test_parse_duty(
    text: str,
    pct: float | None,
    specific: float | None,
    unit: str | None,
    compound: bool,
    resolved: bool,
    additive: bool,
) -> None:
    d = T.parse_duty(text)
    assert d is not None
    assert d.ad_valorem_pct == pct
    assert d.specific_amount == specific
    assert d.specific_unit == unit
    assert d.is_compound is compound
    assert d.is_resolved is resolved
    assert d.additive is additive


@pytest.mark.parametrize("text", ["", "   ", "p/st"])
def test_parse_duty_rejects_non_duties(text: str) -> None:
    assert T.parse_duty(text) is None


def test_parse_special_splits_programs_and_spaces() -> None:
    segs = T.parse_special("Free (AU,BH, CL,CO,E*,IL,JO, KR,MA,OM, P,PA,PE,S,SG)")
    assert len(segs) == 1
    duty, codes = segs[0]
    assert duty.ad_valorem_pct == 0.0
    assert codes == [
        "AU",
        "BH",
        "CL",
        "CO",
        "E*",
        "IL",
        "JO",
        "KR",
        "MA",
        "OM",
        "P",
        "PA",
        "PE",
        "S",
        "SG",
    ]


def test_parse_special_reads_several_segments() -> None:
    segs = T.parse_special("Free (A+,AU,BH) 3.5% (KR)")
    assert [(d.ad_valorem_pct, c) for d, c in segs] == [(0.0, ["A+", "AU", "BH"]), (3.5, ["KR"])]


# --- countries in text --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("articles the product of Bangladesh", ["BGD"]),
        ("articles the product of China and Hong Kong", ["CHN", "HKG"]),
        ("articles the product of Hong Kong, China, as provided", ["HKG"]),
        ("Bangladesh, Botswana, Liechtenstein, or Serbia", ["BGD", "BWA", "LIE", "SRB"]),
        ("From the Socialist Republic of Vietnam: Preliminary", ["VNM"]),
        ("From the Republic of Türkiye: Preliminary", ["TUR"]),
        ("From China, Malaysia, and Turkey; Determinations", ["CHN", "MYS", "TUR"]),
        ("no country here at all", []),
    ],
)
def test_countries_in(text: str, expected: list[str]) -> None:
    assert T.countries_in(text) == expected


def test_iso2_to_iso3() -> None:
    assert T.iso3_of_iso2("BD") == "BGD"
    assert T.iso3_of_iso2("VN") == "VNM"
    assert T.iso3_of_iso2("XC") is None  # UK-only code (Ceuta): no ISO3, kept as ISO2


# --- US HTS: base schedule ----------------------------------------------------------------------

HTS_BASE = "hts_export_6109.json"
HTS_99 = "hts_export_9903_01_07.json"


@pytest.fixture(scope="module")
def hts_base() -> list:
    ctx = _ctx("DS-TRADE-05", HTS_BASE)
    return T.hts_parser("hts:6109")(sample_bytes("DS-TRADE-05", HTS_BASE), ctx)


def test_hts_nomenclature_tree(hts_base: list) -> None:
    nom = {r.code: r for r in _of(hts_base, TariffNomenclatureRecord)}
    assert nom["6109"].level == 4 and nom["6109"].parent_code is None and nom["6109"].hs6 is None
    line = nom["61091000"]
    assert (line.level, line.hs6, line.parent_code, line.code_display) == (
        8,
        "610910",
        "6109",
        "6109.10.00",
    )
    stat = nom["6109100004"]
    assert stat.level == 10 and stat.parent_code == "61091000" and stat.is_declarable
    assert all(r.market_iso3 == "USA" for r in nom.values())
    # rows without an HTS number (description-only headers) are not codes
    assert all(r.code.isdigit() for r in nom.values())


def test_hts_base_rates_for_cotton_tshirts(hts_base: list) -> None:
    ms = [m for m in _of(hts_base, TariffMeasureRecord) if m.code == "61091000"]
    mfn = [m for m in ms if m.kind == "mfn"]
    assert len(mfn) == 1
    assert mfn[0].ad_valorem_pct == 16.5 and mfn[0].origin_kind == "erga_omnes"
    assert mfn[0].origin_code == "*" and mfn[0].hs6 == "610910" and mfn[0].is_resolved
    col2 = [m for m in ms if m.kind == "column2"]
    assert len(col2) == 1 and col2[0].ad_valorem_pct == 90.0 and col2[0].origin_code == "US-COL2"
    pref = [m for m in ms if m.kind == "preferential"]
    assert sorted(m.origin_code for m in pref) == sorted(
        f"US-SP-{c}"
        for c in ["AU", "BH", "CL", "CO", "IL", "JO", "KR", "MA", "OM", "P", "PA", "PE", "S", "SG"]
    )
    assert {m.ad_valorem_pct for m in pref} == {0.0}


def test_hts_other_lines_keep_their_own_rates(hts_base: list) -> None:
    mfn = {m.code: m.ad_valorem_pct for m in _of(hts_base, TariffMeasureRecord) if m.kind == "mfn"}
    assert mfn["61099010"] == 32.0  # man-made fibres
    assert mfn["61099015"] == 5.6
    assert mfn["61099080"] == 16.0


def test_hts_partial_eligibility_star_is_kept_as_a_condition(hts_base: list) -> None:
    # "E*" = only some articles of the line qualify for CBERA (HTS General Note 3(c))
    e = [
        m
        for m in _of(hts_base, TariffMeasureRecord)
        if m.code == "61099080" and m.origin_code == "US-SP-E"
    ]
    assert len(e) == 1 and e[0].conditions.get("partial_eligibility") is True


def test_hts_program_groups_and_members(hts_base: list) -> None:
    groups = {g.group_code: g for g in _of(hts_base, TariffOriginGroupRecord)}
    members = _of(hts_base, TariffOriginMemberRecord)
    by_group: dict[str, set[str | None]] = {}
    for m in members:
        by_group.setdefault(m.group_code, set()).add(m.member_iso3)
    assert by_group["US-SP-S"] == {"CAN", "MEX"}  # USMCA
    assert by_group["US-SP-AU"] == {"AUS"}
    assert "BGD" not in set().union(*by_group.values())
    for m in members:
        assert m.group_id == groups[m.group_code].id
    # every group a measure points at exists, with the same id
    for meas in _of(hts_base, TariffMeasureRecord):
        if meas.origin_kind == "group":
            assert meas.origin_group_id == groups[meas.origin_code].id


def test_hts_snapshot_lists_exactly_its_measures(hts_base: list) -> None:
    (snap,) = _of(hts_base, TariffSnapshotRecord)
    ids = {str(m.id) for m in _of(hts_base, TariffMeasureRecord)}
    assert set(snap.measure_ids) == ids and snap.n_measures == len(ids)
    assert snap.scope == "hts:6109" and snap.market_iso3 == "USA"
    assert all(m.snapshot_scope == "hts:6109" for m in _of(hts_base, TariffMeasureRecord))


# --- US HTS: Chapter 99 country surcharges ------------------------------------------------------


@pytest.fixture(scope="module")
def hts99() -> list:
    ctx = _ctx("DS-TRADE-05", HTS_99)
    return T.hts_parser("hts:9903.01-9903.07")(sample_bytes("DS-TRADE-05", HTS_99), ctx)


def _m99(records: list, ref: str) -> list[TariffMeasureRecord]:
    return [m for m in _of(records, TariffMeasureRecord) if m.measure_ref == ref]


def test_ch99_current_bangladesh_surcharge(hts99: list) -> None:
    (m,) = _m99(hts99, "9903.05.26")
    assert (m.kind, m.code, m.origin_kind, m.origin_code) == ("additional", "*", "country", "BGD")
    assert m.ad_valorem_pct == 10.0 and m.status == "in_force" and m.is_resolved
    assert "9903.05.85–9903.05.92" in m.conditions["except"]
    assert "9903.06.12–9903.06.13" in m.conditions["except"]
    assert m.conditions["note"] == "U.S. note 52"


def test_ch99_terminated_surcharge_one_row_per_country(hts99: list) -> None:
    ms = _m99(hts99, "9903.01.66")
    assert sorted(m.origin_code for m in ms) == ["BGD", "BWA", "LIE", "SRB"]
    for m in ms:
        assert m.ad_valorem_pct == 37.0 and m.status == "terminated"
        assert m.conditions["loaded_before"] == "2025-04-09"
        assert "90 Fed. Reg. 37963" in (m.legal_ref or "")


def test_ch99_expired_window_is_terminated_with_valid_to(hts99: list) -> None:
    (m,) = _m99(hts99, "9903.02.05")
    assert m.ad_valorem_pct == 20.0 and m.origin_code == "BGD"
    assert m.conditions["loaded_before"] == "2025-08-07"
    assert m.valid_to == dt.date(2025, 10, 4)  # entered before 12:01 a.m. on 5 Oct 2025
    assert m.status == "terminated"


def test_ch99_exemptions_are_unresolved(hts99: list) -> None:
    ms = _m99(hts99, "9903.06.12")
    assert len(ms) == 1 and ms[0].kind == "exemption" and ms[0].origin_code == "BGD"
    assert ms[0].ad_valorem_pct == 0.0
    assert ms[0].is_resolved is False  # the note-52 (j)(9) conditions are not read yet
    assert ms[0].conditions["note_ref"] == "(j)(9)(i)"


def test_ch99_competitor_surcharges(hts99: list) -> None:
    current = {
        (m.origin_code): m.ad_valorem_pct
        for m in _of(hts99, TariffMeasureRecord)
        if m.kind == "additional"
        and m.status == "in_force"
        and m.conditions.get("note") == "U.S. note 52"
    }
    assert current["BGD"] == 10.0
    assert current["KHM"] == 10.0
    assert current["IND"] == 10.0
    assert current["VNM"] == 12.5
    assert current["CHN"] == 12.5
    assert current["HKG"] == 12.5


def test_ch99_hong_kong_china_is_not_also_china(hts99: list) -> None:
    assert [m.origin_code for m in _m99(hts99, "9903.05.43")] == ["HKG"]


def test_ch99_lines_without_a_country_are_skipped_unless_a_category(hts99: list) -> None:
    for m in _of(hts99, TariffMeasureRecord):
        if m.origin_kind != "country":
            assert m.kind == "exemption" and m.conditions.get("category")
        else:
            assert len(m.origin_code) == 3


# --- UK Trade Tariff ----------------------------------------------------------------------------

UK = "uk_commodity_6109100010.json"


@pytest.fixture(scope="module")
def uk() -> list:
    return T.parse_uk_commodity(sample_bytes("DS-TRADE-07", UK), _ctx("DS-TRADE-07", UK))


def _uk(records: list, origin: str) -> list[TariffMeasureRecord]:
    return [m for m in _of(records, TariffMeasureRecord) if m.origin_code == origin]


def test_uk_leaf_nomenclature(uk: list) -> None:
    (leaf,) = [n for n in _of(uk, TariffNomenclatureRecord) if n.code == "6109100010"]
    assert leaf.market_iso3 == "GBR" and leaf.hs6 == "610910" and leaf.is_declarable
    assert leaf.level == 10 and leaf.suffix == "80"


def test_uk_mfn_and_dcts(uk: list) -> None:
    (mfn,) = [m for m in _uk(uk, "*") if m.kind == "mfn"]
    assert mfn.ad_valorem_pct == 12.0 and mfn.valid_from == dt.date(2021, 1, 1)
    assert mfn.measure_ref == "20008197" and mfn.code == "6109100010"
    (std,) = _uk(uk, "1060")
    (comp,) = _uk(uk, "1062")
    assert std.kind == comp.kind == "preferential"
    assert std.ad_valorem_pct == 9.6 and comp.ad_valorem_pct == 0.0
    assert comp.valid_from == dt.date(2023, 6, 19) and comp.legal_ref == "U2305610"


def test_uk_bangladesh_is_in_dcts_comprehensive(uk: list) -> None:
    groups = {g.group_code: g for g in _of(uk, TariffOriginGroupRecord)}
    assert "Comprehensive" in groups["1062"].name
    members = {(m.group_code, m.member_iso3) for m in _of(uk, TariffOriginMemberRecord)}
    assert ("1062", "BGD") in members
    assert ("1060", "BGD") not in members


def test_uk_competitor_ftas_and_dates(uk: list) -> None:
    (vn,) = _uk(uk, "VNM")
    assert vn.kind == "preferential" and vn.ad_valorem_pct == 0.0
    assert vn.valid_from == dt.date(2025, 1, 1)
    (india,) = _uk(uk, "IND")
    assert india.valid_from == dt.date(2026, 7, 15)
    (md,) = _uk(uk, "MDA")
    assert md.valid_to == dt.date(2029, 7, 31)


def test_uk_kinds(uk: list) -> None:
    kinds = Counter(m.kind for m in _of(uk, TariffMeasureRecord))
    assert kinds["mfn"] == 2  # erga omnes 12 % and group 1080 0 %
    assert kinds["quota"] == 3  # CR, NI, PA
    assert kinds["additional"] == 2  # Russia and Belarus +35 %
    assert kinds["suspension"] == 1
    # VAT, supplementary units and entry restrictions are not duties
    assert all(m.kind != "other" for m in _of(uk, TariffMeasureRecord))
    (ru,) = _uk(uk, "RUS")
    assert ru.kind == "additional" and ru.ad_valorem_pct == 35.0


def test_uk_excluded_countries_and_unresolved_suspension(uk: list) -> None:
    (g1034,) = _uk(uk, "1034")
    assert g1034.conditions["excluded"] == ["KM"]
    (susp,) = [m for m in _of(uk, TariffMeasureRecord) if m.kind == "suspension"]
    assert susp.is_resolved is False  # end-use conditions apply


def test_uk_groups_referenced_by_measures_exist(uk: list) -> None:
    groups = {g.group_code: g.id for g in _of(uk, TariffOriginGroupRecord)}
    for m in _of(uk, TariffMeasureRecord):
        if m.origin_kind == "group":
            assert groups[m.origin_code] == m.origin_group_id


def test_uk_snapshot(uk: list) -> None:
    (snap,) = _of(uk, TariffSnapshotRecord)
    assert snap.scope == "uk:6109100010" and snap.market_iso3 == "GBR"
    assert snap.n_measures == len(_of(uk, TariffMeasureRecord))


def test_uk_heading_lists_declarable_leaves() -> None:
    name = "uk_heading_6109.json"
    recs = T.parse_uk_heading(sample_bytes("DS-TRADE-07", name), _ctx("DS-TRADE-07", name))
    leaves = T.uk_declarable_leaves(sample_bytes("DS-TRADE-07", name))
    assert "6109100010" in leaves
    assert all(code.startswith("6109") and len(code) == 10 for code in leaves)
    nom = {r.code for r in _of(recs, TariffNomenclatureRecord)}
    assert set(leaves) <= nom


# --- WITS MFN -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wits_eu() -> list:
    name = "mfn_eun_2023.xml"
    return T.parse_wits_mfn(sample_bytes("DS-TRADE-04", name), _ctx("DS-TRADE-04", name))


def test_wits_eu_mfn(wits_eu: list) -> None:
    by = {m.hs6: m for m in _of(wits_eu, TariffMeasureRecord)}
    assert len(by) == 22  # all watched codes since HS 960290 → 960200 (Q-26)
    assert "960200" in by and "960290" not in by
    tee = by["610910"]
    assert tee.market_iso3 == "EUN" and tee.kind == "mfn" and tee.ad_valorem_pct == 12.0
    assert tee.valid_from == dt.date(2023, 1, 1) and tee.valid_to == dt.date(2023, 12, 31)
    assert tee.measure_ref == "WITS:TRN:2023" and tee.conditions["simple_average_of_lines"] == 1
    assert by["620342"].conditions["simple_average_of_lines"] == 7
    assert by["300490"].ad_valorem_pct == 0.0


def test_wits_reporters_map_to_markets() -> None:
    for name, market in [
        ("mfn_usa_2023.xml", "USA"),
        ("mfn_jpn_2023.xml", "JPN"),
        ("mfn_can_2023.xml", "CAN"),
    ]:
        recs = T.parse_wits_mfn(sample_bytes("DS-TRADE-04", name), _ctx("DS-TRADE-04", name))
        assert {m.market_iso3 for m in _of(recs, TariffMeasureRecord)} == {market}
    usa = T.parse_wits_mfn(
        sample_bytes("DS-TRADE-04", "mfn_usa_2023.xml"), _ctx("DS-TRADE-04", "mfn_usa_2023.xml")
    )
    tee = [m for m in _of(usa, TariffMeasureRecord) if m.hs6 == "610910"]
    assert tee[0].ad_valorem_pct == 16.5  # agrees with the HTS line 6109.10.00


# --- Federal Register ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def notices() -> list[TradePolicyNoticeRecord]:
    name = "fr_hts_documents.json"
    recs = T.parse_federal_register(sample_bytes("DS-TRADE-06", name), _ctx("DS-TRADE-06", name))
    return _of(recs, TradePolicyNoticeRecord)


def test_fr_drops_non_trade_agencies(notices: list[TradePolicyNoticeRecord]) -> None:
    assert len(notices) == 19
    assert "2026-22750" not in {n.document_number for n in notices}  # HHS payment rule


def test_fr_kinds_and_countries(notices: list[TradePolicyNoticeRecord]) -> None:
    by = {n.document_number: n for n in notices}
    assert by["2026-23401"].kind == "trade_remedy"
    assert by["2026-23401"].countries == ["CHN", "MYS", "TUR"]
    assert by["2026-22925"].kind == "exclusion"
    assert by["2026-22867"].kind == "tariff_modification"
    assert by["2026-22939"].countries == ["VNM"]
    assert by["2026-23420"].publication_date == dt.date(2026, 11, 18)
    assert by["2026-23420"].market_iso3 == "USA"
    assert by["2026-23420"].url.startswith("https://www.federalregister.gov/")


def test_fr_countries_exclude_the_issuing_market() -> None:
    recs = T.parse_federal_register(
        b'{"results": [{"document_number": "x-1", "title": "Steel From India Imported Into the '
        b'United States", "publication_date": "2026-11-01", "html_url": "https://www.federalregi'
        b'ster.gov/d/x-1", "agencies": [{"slug": "international-trade-administration"}]}]}',
        ParseContext("DS-TRADE-06", DataMode.REPLAY),
    )
    assert [r.countries for r in recs] == [["IND"]]


# --- identity and lineage -----------------------------------------------------------------------


def test_measure_ids_are_versioned_by_content(hts99: list) -> None:
    ctx = _ctx("DS-TRADE-05", HTS_99)
    body = sample_bytes("DS-TRADE-05", HTS_99)
    changed = body.replace(b"applicable subheading + 10%", b"applicable subheading + 15%", 1)
    again = T.hts_parser("hts:9903.01-9903.07")(body, ctx)
    edited = T.hts_parser("hts:9903.01-9903.07")(changed, ctx)
    ids = {m.id for m in _of(again, TariffMeasureRecord)}
    assert ids == {m.id for m in _of(hts99, TariffMeasureRecord)}  # deterministic
    new_ids = {m.id for m in _of(edited, TariffMeasureRecord)}
    assert len(ids - new_ids) >= 1 and len(new_ids - ids) >= 1  # the edited line re-keys
    assert T.natural_key(next(iter(_of(edited, TariffMeasureRecord)))) is not None


def test_lineage_is_replay_and_has_available_at(hts99: list, uk: list) -> None:
    for r in [*hts99, *uk]:
        assert r.data_mode == "replay" and not r.is_synthetic and r.available_at is not None


def test_hts_heading_scope_drops_the_next_headings_row(hts_base: list) -> None:
    # exportList's `to` is exclusive but still returns the next heading's header row
    codes = {r.code for r in _of(hts_base, TariffNomenclatureRecord)}
    assert "6110" not in codes and all(c.startswith("6109") for c in codes)


# --- EU preferences (manual table, DS-TRADE-08) -------------------------------------------------


@pytest.fixture(scope="module")
def eu_prefs() -> list:
    from cportal_core.paths import config_dir

    body = (config_dir() / "tariffs" / "eu_preferences.yaml").read_bytes()
    return T.parse_eu_preferences(body, ParseContext("DS-TRADE-08", DataMode.REPLAY))


def test_eu_eba_bangladesh_with_transition_end(eu_prefs: list) -> None:
    members = [m for m in _of(eu_prefs, TariffOriginMemberRecord) if m.member_iso3 == "BGD"]
    assert [(m.group_code, m.valid_to) for m in members] == [("EU-EBA", dt.date(2029, 11, 24))]
    (eba,) = [m for m in _of(eu_prefs, TariffMeasureRecord) if m.origin_code == "EU-EBA"]
    assert eba.kind == "preferential" and eba.ad_valorem_pct == 0.0 and eba.code == "*"
    assert eba.conditions["exclude_chapters"] == ["93"] and eba.conditions["verify"] is True
    assert eba.market_iso3 == "EUN" and "978/2012" in (eba.legal_ref or "")


def test_eu_relative_and_staged_rates_stay_unresolved(eu_prefs: list) -> None:
    by = {m.origin_code: m for m in _of(eu_prefs, TariffMeasureRecord)}
    gsp = by["EU-GSP"]
    assert gsp.is_resolved is False and gsp.ad_valorem_pct is None
    assert gsp.conditions["mfn_reduction_pct"] == 20
    assert gsp.conditions["include_chapters"] == ["61", "62", "63"]
    vn = by["EU-VN-FTA"]
    assert vn.is_resolved is False and vn.ad_valorem_pct is None


def test_eu_prefs_snapshot_and_lineage(eu_prefs: list) -> None:
    (snap,) = _of(eu_prefs, TariffSnapshotRecord)
    assert snap.scope == "eu-prefs" and snap.n_measures == 4
    assert all(r.source_id == "DS-TRADE-08" for r in eu_prefs)


# --- live HTTP keeps a query string built into the URL (Federal Register fields[]) -------------


def test_live_get_keeps_the_urls_own_query_string(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import httpx
    from cportal_connectors.live import LiveHttp
    from cportal_connectors.sources.ds_trade_06_federal_register import documents_url
    from cportal_core.settings import get_settings

    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"results": []})

    http = LiveHttp(
        "DS-TRADE-06",
        get_settings(),
        min_interval_s=0.001,
        transport=httpx.MockTransport(handler),
        root=tmp_path,
    )
    http.get("fr", documents_url(5))
    http.close()
    q = seen[0].params
    assert q.get("conditions[term]") == '"Harmonized Tariff Schedule"'
    assert q.get_list("fields[]")[:2] == ["document_number", "title"]
    assert q.get("per_page") == "5"


def test_ch99_category_exemptions_cover_their_chapters(hts99: list) -> None:
    (pharma,) = _m99(hts99, "9903.05.89")
    assert (pharma.kind, pharma.code, pharma.origin_kind) == ("exemption", "*", "erga_omnes")
    assert pharma.conditions["include_chapters"] == ["29", "30"]
    assert pharma.conditions["category"] == "pharmaceutical applications"
    assert pharma.conditions["note_ref"] == "(e)" and pharma.is_resolved is False
    # 9903.05.90 lists several Section 232 categories: metals and patented pharmaceuticals
    (s232,) = _m99(hts99, "9903.05.90")
    assert s232.conditions["include_chapters"] == ["29", "30", "72", "73", "74", "76"]
    assert "pharmaceutical" in s232.conditions["category"]
    assert "aluminium" in s232.conditions["category"]
    # donations and informational materials are not product categories: not stored
    assert _m99(hts99, "9903.05.91") == [] and _m99(hts99, "9903.05.92") == []
