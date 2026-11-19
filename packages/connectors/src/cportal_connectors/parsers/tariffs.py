"""C6 tariff parsers (ADR-021): official schedules → nomenclature, measures, groups, snapshots.

Sources (probed 2026-11-18, samples in data/samples/DS-TRADE-04…07):

- DS-TRADE-04 WITS TRAINS SDMX: reported MFN averages by HS6, one series per product.
- DS-TRADE-05 USITC HTS REST `exportList`: the US schedule; ordinary lines carry the general,
  special (preference programmes) and column-2 rates; Chapter 99 lines (9903.xx) carry country
  surcharges and their exemptions in legal prose, which is read with narrow, tested patterns.
- DS-TRADE-06 Federal Register API: official notices (trade agencies only).
- DS-TRADE-07 UK Trade Tariff API v2: one commodity's measures with origin groups and members.

Principles: the verbatim duty text is always kept; a rate that is not a plain ad valorem
percentage is stored with `is_resolved = False` so nothing downstream guesses a number; a
measure's id includes a hash of its content, so a changed rate becomes a new row (history) and
the snapshot of its scope says which rows were current when.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any
from uuid import UUID

import yaml
from cportal_core.enums import (
    TariffMeasureKind,
    TariffOriginKind,
    TariffStatus,
    TradeNoticeKind,
)
from cportal_core.paths import config_dir
from cportal_core.schemas.records import (
    Record,
    TariffMeasureRecord,
    TariffNomenclatureRecord,
    TariffOriginGroupRecord,
    TariffOriginMemberRecord,
    TariffSnapshotRecord,
    TradePolicyNoticeRecord,
)
from defusedxml import ElementTree as ET  # external XML: no entities, no expansion

from cportal_connectors.canonical import ParseContext, Parser, parse_ts

PARSER_VERSION = "c6-parsers-3"  # 3: UK exclusions as ISO3; EU refs by rule scope
"""Stamped on every snapshot. Bump it when parsing reads a schedule differently (e.g. 2 added
Chapter 99 category exemptions): C6 does not diff snapshots made by different versions, so a
parser upgrade re-baselines instead of showing up as tariff changes (A-133)."""

# --- duty text ----------------------------------------------------------------------------------

_NUM = r"(\d+(?:\.\d+)?)"
_PCT = re.compile(_NUM + r"\s*%")
# "3.4¢/kg", "1.20 GBP / 100 kg", "$1.50/doz."
_SPECIFIC = re.compile(
    r"(?:\$\s*" + _NUM + r"|" + _NUM + r"\s*(¢|GBP|EUR|USD|\$))\s*/\s*(\d*\s*[A-Za-z][A-Za-z.]*)"
)
_ADDITIVE = "the duty provided in the applicable subheading"


@dataclass(frozen=True)
class Duty:
    ad_valorem_pct: float | None
    specific_amount: float | None
    specific_unit: str | None
    is_compound: bool
    is_resolved: bool  # True only when the whole duty is one ad valorem percentage
    additive: bool  # True when it adds to the ordinary rate (US Chapter 99)


def _float(v: str | None) -> float | None:
    """A reported number, or None (missing, empty or not a finite number)."""
    try:
        x = float(v) if v not in (None, "") else None
    except ValueError:
        return None
    return x if x is not None and math.isfinite(x) else None


def parse_duty(text: str) -> Duty | None:
    """Read a duty expression; None when the text is not a duty (empty, a unit like "p/st")."""
    t = " ".join((text or "").split())
    if not t:
        return None
    low = t.lower()
    if low.startswith(_ADDITIVE):
        m = re.search(r"\+\s*" + _NUM + r"\s*%", t)
        return Duty(float(m.group(1)) if m else 0.0, None, None, False, True, True)
    if low == "free":
        return Duty(0.0, None, None, False, True, False)
    pct_m = _PCT.search(t)
    spec_m = _SPECIFIC.search(t)
    if pct_m is None and spec_m is None:
        return None
    pct = float(pct_m.group(1)) if pct_m else None
    amount: float | None = None
    unit: str | None = None
    if spec_m is not None:
        if spec_m.group(1) is not None:  # "$1.50/doz."
            amount, unit = float(spec_m.group(1)), f"$/{spec_m.group(4).strip()}"
        else:
            amount = float(spec_m.group(2))
            unit = f"{spec_m.group(3)}/{spec_m.group(4).strip()}"
    compound = pct is not None and amount is not None
    return Duty(pct, amount, unit, compound, amount is None, False)


_SPECIAL_SEG = re.compile(r"(Free|\d+(?:\.\d+)?\s*%[^()]*?|[^()]*?)\s*\(([^)]*)\)")


def parse_special(text: str) -> list[tuple[Duty, list[str]]]:
    """US "Special" column: "Free (AU,BH, CL) 3.5% (KR)" → [(Free, [AU, BH, CL]), (3.5%, [KR])]."""
    out: list[tuple[Duty, list[str]]] = []
    for rate, codes in _SPECIAL_SEG.findall(" ".join((text or "").split())):
        duty = parse_duty(rate.strip())
        if duty is None:
            continue
        out.append((duty, [c.strip() for c in codes.split(",") if c.strip()]))
    return out


# --- countries ----------------------------------------------------------------------------------


@cache
def _countries() -> dict[str, dict[str, Any]]:
    with (config_dir() / "tariffs" / "countries.yaml").open(encoding="utf-8") as fh:
        data: dict[str, dict[str, Any]] = yaml.safe_load(fh)["countries"]
    return data


@cache
def _name_patterns() -> list[tuple[re.Pattern[str], str]]:
    pairs = [(name, iso3) for iso3, c in _countries().items() for name in c["names"]]
    pairs.sort(key=lambda p: -len(p[0]))  # longest first: "Hong Kong, China" before "China"
    return [(re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])"), iso3) for n, iso3 in pairs]


def countries_in(text: str) -> list[str]:
    """ISO3 codes of the countries named in a text, in order of first mention."""
    buf = text or ""
    found: dict[str, int] = {}
    for pattern, iso3 in _name_patterns():
        for m in pattern.finditer(buf):
            found.setdefault(iso3, m.start())
            found[iso3] = min(found[iso3], m.start())
        buf = pattern.sub(lambda m: " " * len(m.group(0)), buf)  # a span counts once
    return [iso3 for iso3, _ in sorted(found.items(), key=lambda kv: kv[1])]


@cache
def _iso2_map() -> dict[str, str]:
    return {c["iso2"]: iso3 for iso3, c in _countries().items() if c.get("iso2")}


def iso3_of_iso2(iso2: str) -> str | None:
    return _iso2_map().get(iso2.upper())


# --- identity -----------------------------------------------------------------------------------


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def natural_key(m: TariffMeasureRecord) -> tuple[str, str, str, str, str]:
    """What makes two measure versions "the same rule" across snapshots (for diffs)."""
    return (m.market_iso3, m.code, str(m.kind), m.origin_code, m.measure_ref)


def _measure(ctx: ParseContext, scope: str, **kw: Any) -> TariffMeasureRecord:
    content = {
        k: kw.get(k)
        for k in (
            "duty_text",
            "ad_valorem_pct",
            "specific_amount",
            "specific_unit",
            "status",
            "valid_from",
            "valid_to",
            "conditions",
            "legal_ref",
        )
    }
    h = _hash(content)
    key = "|".join(
        [kw["market_iso3"], kw["code"], str(kw["kind"]), kw["origin_code"], kw["measure_ref"]]
    )
    return TariffMeasureRecord(
        id=ctx.rid("tariff_measure", f"{key}|{h}"),
        **ctx.lineage(source_record_id=key),
        content_hash=h,
        snapshot_scope=scope,
        **kw,
    )


def _snapshot(
    ctx: ParseContext, market: str, scope: str, measures: list[TariffMeasureRecord]
) -> TariffSnapshotRecord:
    fetched = ctx.fetched_at or dt.datetime.now(dt.UTC)
    ids = sorted(str(m.id) for m in measures)
    lineage = ctx.lineage(source_record_id=scope)
    if not ctx.is_synthetic:
        lineage["generator_version"] = PARSER_VERSION
    # the content is part of the id: a hand-kept table edited without moving its as_of date is
    # a new snapshot (C6 orders equal fetch times by updated_at), not an overwrite (review #6)
    return TariffSnapshotRecord(
        id=ctx.rid("tariff_snapshot", f"{scope}|{fetched.isoformat()}|{_hash(ids)}"),
        **lineage,
        market_iso3=market,
        scope=scope,
        fetched_at=fetched,
        measure_ids=ids,
        n_measures=len(ids),
        content_hash=_hash(ids),
    )


def _group(
    ctx: ParseContext,
    market: str,
    code: str,
    name: str,
    scheme: str | None,
    members: Iterable[tuple[str | None, str | None]],
    notes: str | None = None,
) -> list[Record]:
    gid = group_id(ctx, market, code)
    out: list[Record] = [
        TariffOriginGroupRecord(
            id=gid,
            **ctx.lineage(source_record_id=f"{market}|{code}"),
            market_iso3=market,
            group_code=code,
            name=name,
            scheme=scheme,
            notes=notes,
        )
    ]
    for iso2, iso3 in members:
        key = f"{market}|{code}|{iso2 or ''}|{iso3 or ''}"
        out.append(
            TariffOriginMemberRecord(
                id=ctx.rid("tariff_origin_member", key),
                **ctx.lineage(source_record_id=key),
                group_id=gid,
                market_iso3=market,
                group_code=code,
                member_iso2=iso2,
                member_iso3=iso3,
            )
        )
    return out


def group_id(ctx: ParseContext, market: str, code: str) -> UUID:
    return ctx.rid("tariff_origin_group", f"{market}|{code}")


def _date(value: Any) -> dt.date | None:
    ts = parse_ts(value)
    return None if ts is None else ts.date()


# --- US HTS -------------------------------------------------------------------------------------

USA = "USA"
_TAGS = re.compile(r"<[^>]+>")
_TERMINATED = re.compile(r"provision terminated", re.I)
_FR_CITE = re.compile(r"(\d+ Fed\. Reg\. \d+)")
_HEADING_REF = re.compile(r"99\d\d\.\d\d\.\d\d(?:\s*[–-]\s*99\d\d\.\d\d\.\d\d)?")
_NOTE = re.compile(r"U\.S\. note (\d+)")
_SUBDIV = re.compile(r"subdivision ((?:\([a-z0-9]+\))+)")
_US_DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"
_LOADED = re.compile(r"loaded onto a vessel.*?before 12:01 a\.m\. eastern \w+ time on " + _US_DATE)
_ENTERED = re.compile(
    r"entered for consumption.*?before 12:01 a\.m\. eastern \w+ time on " + _US_DATE
)
_PRODUCT_OF = re.compile(r"products? of\s+(.*)", re.I | re.S)
_PRODUCT_OF_END = re.compile(
    r",?\s+(?:as provided|that\b|which\b|classified|entered|loaded|described|\()", re.I
)


@cache
def _us_programs() -> dict[str, Any]:
    with (config_dir() / "tariffs" / "us_programs.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def _us_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, "%B %d, %Y").date()


def _us_groups(ctx: ParseContext, used: set[str]) -> list[Record]:
    cfg = _us_programs()
    out: list[Record] = []
    for code in sorted(used):
        if code == cfg["column2"]["group"]:
            c2 = cfg["column2"]
            members = [(_countries().get(i, {}).get("iso2"), i) for i in c2["members"]]
            out += _group(ctx, USA, code, c2["name"], "column2", members, c2.get("notes"))
            continue
        prog = code.removeprefix("US-SP-")
        p = cfg["programs"].get(prog)
        if p is None:
            out += _group(
                ctx,
                USA,
                code,
                f"Unknown HTS programme {prog}",
                None,
                [],
                "not in config/tariffs/us_programs.yaml",
            )
            continue
        members = [(_countries().get(i, {}).get("iso2"), i) for i in p.get("members", [])]
        out += _group(ctx, USA, code, p["name"], p.get("scheme"), members, p.get("notes"))
    return out


def _program_code(code: str) -> tuple[str, bool]:
    """HTS special indicator → (programme key, partial eligibility). "E*" = some articles only
    (General Note 3(c)); "A*" and "A+" are their own GSP variants."""
    programs = _us_programs()["programs"]
    if code in programs:
        return code, False
    if code.endswith("*") and code[:-1] in programs:
        return code[:-1], True
    return code, False


def _base_measures(
    ctx: ParseContext, scope: str, row: dict[str, Any], code: str, used: set[str]
) -> list[TariffMeasureRecord]:
    htsno = row["htsno"]
    common = {
        "market_iso3": USA,
        "code": code,
        "hs6": code[:6] if len(code) >= 6 else None,
        "measure_ref": htsno,
        "source_url": f"https://hts.usitc.gov/search?query={htsno}",
        "status": TariffStatus.IN_FORCE,
    }
    out: list[TariffMeasureRecord] = []

    def add(
        kind: TariffMeasureKind,
        origin_kind: TariffOriginKind,
        origin: str,
        text: str,
        duty: Duty,
        legal: str,
        conditions: dict[str, Any] | None = None,
    ) -> None:
        gid = group_id(ctx, USA, origin) if origin_kind == TariffOriginKind.GROUP else None
        if gid is not None:
            used.add(origin)
        out.append(
            _measure(
                ctx,
                scope,
                kind=kind,
                origin_kind=origin_kind,
                origin_code=origin,
                origin_group_id=gid,
                duty_text=text,
                ad_valorem_pct=duty.ad_valorem_pct,
                specific_amount=duty.specific_amount,
                specific_unit=duty.specific_unit,
                is_compound=duty.is_compound,
                is_resolved=duty.is_resolved,
                legal_ref=legal,
                conditions=conditions or {},
                **common,
            )
        )

    general = parse_duty(row.get("general") or "")
    if general is None and (row.get("general") or "").strip():
        # text that is not a duty ("See 9903.88.15"): keep the line, with no number, rather
        # than drop it and let the cell look resolved without it (review 2026-11-19 #13)
        general = Duty(None, None, None, False, False, False)
    if general is not None:
        add(
            TariffMeasureKind.MFN,
            TariffOriginKind.ERGA_OMNES,
            "*",
            row["general"],
            general,
            f"HTSUS {htsno}, column 1 general",
        )
    other = parse_duty(row.get("other") or "")
    if other is not None:
        add(
            TariffMeasureKind.COLUMN2,
            TariffOriginKind.GROUP,
            _us_programs()["column2"]["group"],
            row["other"],
            other,
            f"HTSUS {htsno}, column 2",
        )
    for duty, codes in parse_special(row.get("special") or ""):
        for raw in codes:
            prog, partial = _program_code(raw)
            add(
                TariffMeasureKind.PREFERENTIAL,
                TariffOriginKind.GROUP,
                f"US-SP-{prog}",
                f"{duty_text_of(duty)} ({raw})",
                duty,
                f"HTSUS {htsno}, column 1 special",
                {"partial_eligibility": True} if partial else None,
            )
    return out


def duty_text_of(d: Duty) -> str:
    if d.ad_valorem_pct == 0 and d.specific_amount is None:
        return "Free"
    parts = []
    if d.specific_amount is not None:
        parts.append(f"{d.specific_amount:g}{d.specific_unit or ''}")
    if d.ad_valorem_pct is not None:
        parts.append(f"{d.ad_valorem_pct:g}%")
    return " + ".join(parts)


def _ch99_measures(ctx: ParseContext, scope: str, row: dict[str, Any]) -> list[TariffMeasureRecord]:
    duty = parse_duty(row.get("general") or "")
    if duty is None or not duty.additive:
        return []
    desc = " ".join(_TAGS.sub(" ", row.get("description") or "").split())
    m = _PRODUCT_OF.search(desc)
    countries = countries_in(_PRODUCT_OF_END.split(m.group(1), maxsplit=1)[0]) if m else []
    if not countries:
        return _category_exemption(ctx, scope, row, desc, duty)
    assert m is not None  # countries come only from a "product of" match
    head = desc[: m.start()]
    conditions: dict[str, Any] = {}
    if head.lower().startswith("except") or " except " in head.lower():
        refs = _HEADING_REF.findall(head)
        if refs:
            conditions["except"] = refs
    if note := _NOTE.search(desc):
        conditions["note"] = f"U.S. note {note.group(1)}"
    if sub := _SUBDIV.search(desc):
        conditions["note_ref"] = sub.group(1)
    valid_from = valid_to = None
    if loaded := _LOADED.search(desc):
        valid_from = _us_date(loaded.group(1))
        conditions["loaded_before"] = valid_from.isoformat()
    if entered := _ENTERED.search(desc):
        valid_to = _us_date(entered.group(1)) - dt.timedelta(days=1)
        conditions["entered_before"] = (valid_to + dt.timedelta(days=1)).isoformat()
    legal = f"HTSUS {row['htsno']}"
    status = TariffStatus.IN_FORCE
    if _TERMINATED.search(desc):
        status = TariffStatus.TERMINATED
        if cite := _FR_CITE.search(desc):
            legal += f"; terminated: {cite.group(1)}"
    elif valid_to and ctx.fetched_at and valid_to < ctx.fetched_at.date():
        status = TariffStatus.TERMINATED
    kind = TariffMeasureKind.ADDITIONAL if duty.ad_valorem_pct else TariffMeasureKind.EXEMPTION
    conditions["text"] = desc[:2000]
    return [
        _measure(
            ctx,
            scope,
            market_iso3=USA,
            code="*",
            hs6=None,
            kind=kind,
            origin_kind=TariffOriginKind.COUNTRY,
            origin_code=iso3,
            origin_group_id=None,
            duty_text=row["general"],
            ad_valorem_pct=duty.ad_valorem_pct,
            specific_amount=None,
            specific_unit=None,
            is_compound=False,
            is_resolved=kind == TariffMeasureKind.ADDITIONAL,
            measure_ref=row["htsno"],
            legal_ref=legal,
            source_url=f"https://hts.usitc.gov/search?query={row['htsno']}",
            status=status,
            valid_from=valid_from,
            valid_to=valid_to,
            conditions=conditions,
        )
        for iso3 in countries
    ]


@cache
def _us_categories() -> list[dict[str, Any]]:
    with (config_dir() / "tariffs" / "us_exemption_categories.yaml").open(encoding="utf-8") as fh:
        data: list[dict[str, Any]] = yaml.safe_load(fh)["categories"]
    return data


def _category_exemption(
    ctx: ParseContext, scope: str, row: dict[str, Any], desc: str, duty: Duty
) -> list[TariffMeasureRecord]:
    """A Chapter 99 exemption for a product category whose HS list sits in a U.S. note: kept
    as an unresolved exemption limited to the chapters the category plausibly covers."""
    if duty.ad_valorem_pct:
        return []
    low = desc.lower()
    cats = [c for c in _us_categories() if c["match"] in low]
    if not cats:
        return []
    conditions: dict[str, Any] = {
        "include_chapters": sorted({ch for c in cats for ch in c["chapters"]}),
        "category": "; ".join(c["label"] for c in cats),
        "chapters_are_estimate": True,
        "text": desc[:2000],
    }
    if note := _NOTE.search(desc):
        conditions["note"] = f"U.S. note {note.group(1)}"
    if sub := _SUBDIV.search(desc):
        conditions["note_ref"] = sub.group(1)
    return [
        _measure(
            ctx,
            scope,
            market_iso3=USA,
            code="*",
            hs6=None,
            kind=TariffMeasureKind.EXEMPTION,
            origin_kind=TariffOriginKind.ERGA_OMNES,
            origin_code="*",
            origin_group_id=None,
            duty_text=row["general"],
            ad_valorem_pct=0.0,
            specific_amount=None,
            specific_unit=None,
            is_compound=False,
            is_resolved=False,
            measure_ref=row["htsno"],
            legal_ref=f"HTSUS {row['htsno']}",
            source_url=f"https://hts.usitc.gov/search?query={row['htsno']}",
            status=TariffStatus.IN_FORCE,
            valid_from=None,
            valid_to=None,
            conditions=conditions,
        )
    ]


def hts_parser(scope: str) -> Parser:
    """A parser for one HTS `exportList` range; `scope` names the range for snapshots."""

    def parse(body: bytes, ctx: ParseContext) -> list[Record]:
        rows: list[dict[str, Any]] = json.loads(body)
        nomenclature: list[TariffNomenclatureRecord] = []
        measures: list[TariffMeasureRecord] = []
        used: set[str] = set()
        seen: list[str] = []
        codes = [re.sub(r"\D", "", r.get("htsno") or "") for r in rows]
        if heading := re.fullmatch(r"hts:(\d{4})", scope):  # one heading: drop the next one's row
            codes = [c if c.startswith(heading.group(1)) else "" for c in codes]
        all_codes = {c for c in codes if c}
        for row, code in zip(rows, codes, strict=True):
            if not code:
                continue  # description-only header rows
            if code.startswith("9903"):
                measures += _ch99_measures(ctx, scope, row)
                continue
            parent = next(
                (
                    p
                    for p in sorted(seen, key=len, reverse=True)
                    if code.startswith(p) and p != code
                ),
                None,
            )
            seen.append(code)
            leaf = not any(o != code and o.startswith(code) for o in all_codes)
            nomenclature.append(
                TariffNomenclatureRecord(
                    id=ctx.rid("tariff_nomenclature", f"{USA}|{code}"),
                    **ctx.lineage(source_record_id=row["htsno"]),
                    market_iso3=USA,
                    code=code,
                    code_display=row["htsno"],
                    level=len(code),
                    hs6=code[:6] if len(code) >= 6 else None,
                    parent_code=parent,
                    description=_TAGS.sub("", row.get("description") or "").strip() or "—",
                    is_declarable=leaf,
                )
            )
            measures += _base_measures(ctx, scope, row, code, used)
        out: list[Record] = [*nomenclature, *_us_groups(ctx, used), *measures]
        out.append(_snapshot(ctx, USA, scope, measures))
        return out

    return parse


# --- UK Trade Tariff ----------------------------------------------------------------------------

GBR = "GBR"
UK_ERGA_OMNES = "1011"


def _uk_kind(series: str, description: str) -> TariffMeasureKind | None:
    d = description.lower()
    if series == "C":
        if "third country" in d:
            return TariffMeasureKind.MFN
        if "quota" in d:
            return TariffMeasureKind.QUOTA
        if "preference" in d:
            return TariffMeasureKind.PREFERENTIAL
        if "suspension" in d or "end-use" in d or "end use" in d or "relief" in d:
            return TariffMeasureKind.SUSPENSION
        return TariffMeasureKind.OTHER
    if series == "D":
        return TariffMeasureKind.TRADE_REMEDY
    if series == "J" or "additional dut" in d:
        return TariffMeasureKind.ADDITIONAL
    return None  # VAT, excise, supplementary units, prohibitions and restrictions


def _uk_scheme(description: str) -> str | None:
    if m := re.search(r"DCTS\)? - (\w+)", description):
        return f"DCTS-{m.group(1)}"
    return None


def parse_uk_commodity(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = json.loads(body)
    attrs = doc["data"]["attributes"]
    code = attrs["goods_nomenclature_item_id"]
    scope = f"uk:{code}"
    inc = {(i["type"], i["id"]): i for i in doc.get("included", [])}
    out: list[Record] = [
        TariffNomenclatureRecord(
            id=ctx.rid("tariff_nomenclature", f"{GBR}|{code}|{attrs.get('producline_suffix')}"),
            **ctx.lineage(source_record_id=code),
            market_iso3=GBR,
            code=code,
            code_display=code,
            suffix=attrs.get("producline_suffix"),
            level=10,
            hs6=code[:6],
            parent_code=None,
            description=attrs.get("description_plain") or attrs.get("description") or "—",
            is_declarable=bool(attrs.get("declarable")),
            valid_from=_date(attrs.get("validity_start_date")),
            valid_to=_date(attrs.get("validity_end_date")),
        )
    ]
    measures: list[TariffMeasureRecord] = []
    groups: dict[str, dict[str, Any]] = {}
    for ref in doc["data"]["relationships"].get("import_measures", {}).get("data", []):
        m = inc.get(("measure", ref["id"]))
        if m is None:
            continue
        rel = m["relationships"]
        mt = inc.get(("measure_type", rel["measure_type"]["data"]["id"]), {}).get("attributes", {})
        kind = _uk_kind(str(mt.get("measure_type_series_id")), str(mt.get("description", "")))
        if kind is None:
            continue
        de_ref = (rel.get("duty_expression") or {}).get("data") or {}
        text = inc.get(("duty_expression", de_ref.get("id")), {}).get("attributes", {}).get("base")
        duty = parse_duty(text or "")
        if duty is None:
            continue
        geo = rel["geographical_area"]["data"]["id"]
        gid: UUID | None = None
        if geo == UK_ERGA_OMNES:
            origin_kind, origin = TariffOriginKind.ERGA_OMNES, "*"
        elif geo.isdigit():
            origin_kind, origin = TariffOriginKind.GROUP, geo
            gid = group_id(ctx, GBR, geo)
            area = inc.get(("geographical_area", geo), {})
            groups[geo] = area
        else:
            origin_kind, origin = TariffOriginKind.COUNTRY, iso3_of_iso2(geo) or geo
        # ISO3 like every other origin in C6 (the API gives geographical-area ids: ISO2)
        excluded = [
            iso3_of_iso2(x["id"]) or x["id"]
            for x in rel.get("excluded_countries", {}).get("data", [])
        ]
        n_conditions = len(rel.get("measure_conditions", {}).get("data", []))
        conditions: dict[str, Any] = {"measure_type": mt.get("description")}
        if excluded:
            conditions["excluded"] = excluded
        if n_conditions:
            conditions["n_conditions"] = n_conditions
        legal = [x["id"] for x in rel.get("legal_acts", {}).get("data", [])]
        a = m["attributes"]
        measures.append(
            _measure(
                ctx,
                scope,
                market_iso3=GBR,
                code=code,
                hs6=code[:6],
                kind=kind,
                origin_kind=origin_kind,
                origin_code=origin,
                origin_group_id=gid,
                duty_text=text or "",
                ad_valorem_pct=duty.ad_valorem_pct,
                specific_amount=duty.specific_amount,
                specific_unit=duty.specific_unit,
                is_compound=duty.is_compound,
                is_resolved=(duty.is_resolved and n_conditions == 0)
                or (kind == TariffMeasureKind.QUOTA and duty.is_resolved),
                measure_ref=str(a["id"]),
                legal_ref=legal[0] if legal else None,
                source_url=f"https://www.trade-tariff.service.gov.uk/commodities/{code}",
                status=TariffStatus.IN_FORCE,
                valid_from=_date(a.get("effective_start_date")),
                valid_to=_date(a.get("effective_end_date")),
                conditions=conditions,
            )
        )
    for geo, area in sorted(groups.items()):
        name = area.get("attributes", {}).get("description") or geo
        kids = area.get("relationships", {}).get("children_geographical_areas", {}).get("data", [])
        members = [(k["id"], iso3_of_iso2(k["id"])) for k in kids]
        out += _group(ctx, GBR, geo, name, _uk_scheme(name), members)
    out += measures
    out.append(_snapshot(ctx, GBR, scope, measures))
    return out


def uk_declarable_leaves(body: bytes) -> list[str]:
    """Declarable 10-digit commodity codes in a UK heading document."""
    doc = json.loads(body)
    return sorted(
        {
            i["attributes"]["goods_nomenclature_item_id"]
            for i in doc.get("included", [])
            if i["type"] == "commodity" and i["attributes"].get("declarable")
        }
    )


def parse_uk_heading(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = json.loads(body)
    commodities = [i for i in doc.get("included", []) if i["type"] == "commodity"]
    by_sid = {str(c["attributes"].get("goods_nomenclature_sid")): c for c in commodities}
    head = doc["data"]["attributes"]["goods_nomenclature_item_id"][:4]
    out: list[Record] = []
    for c in commodities:
        a = c["attributes"]
        code = a["goods_nomenclature_item_id"]
        parent = by_sid.get(str(a.get("parent_sid")))
        out.append(
            TariffNomenclatureRecord(
                id=ctx.rid("tariff_nomenclature", f"{GBR}|{code}|{a.get('producline_suffix')}"),
                **ctx.lineage(source_record_id=code),
                market_iso3=GBR,
                code=code,
                code_display=code,
                suffix=a.get("producline_suffix"),
                level=10,
                hs6=code[:6],
                parent_code=parent["attributes"]["goods_nomenclature_item_id"] if parent else head,
                description=a.get("description_plain") or a.get("description") or "—",
                is_declarable=bool(a.get("declarable")),
                valid_from=_date(a.get("validity_start_date")),
                valid_to=_date(a.get("validity_end_date")),
            )
        )
    return out


# --- WITS TRAINS --------------------------------------------------------------------------------

WITS_REPORTERS = {
    "918": "EUN",
    "840": "USA",
    "826": "GBR",
    "392": "JPN",
    "124": "CAN",
    "050": "BGD",
    "156": "CHN",
    "356": "IND",
    "704": "VNM",
    "036": "AUS",
}
"""WITS numeric reporter codes → market codes (the EU is "EUN", as WITS names it)."""


def parse_wits_mfn(body: bytes, ctx: ParseContext) -> list[Record]:
    root = ET.fromstring(body)
    measures: list[TariffMeasureRecord] = []
    market = "UNK"
    years: set[str] = set()
    for series in root.iter():
        if not series.tag.endswith("Series"):
            continue
        market = WITS_REPORTERS.get(series.get("REPORTER", ""), series.get("REPORTER", "UNK"))
        hs6 = series.get("PRODUCTCODE", "")
        for obs in series:
            if not obs.tag.endswith("Obs") or obs.get("TARIFFTYPE") != "MFN":
                continue
            year = obs.get("TIME_PERIOD", "")
            years.add(year)
            value = _float(obs.get("OBS_VALUE"))
            lines = int(obs.get("TOTALNOOFLINES", "0") or 0)
            lo, hi = obs.get("MIN_RATE"), obs.get("MAX_RATE")
            # one number only when it is reported and every national line has it (review #13)
            same = lo is not None and hi is not None and _float(lo) == _float(hi)
            resolved = value is not None and (lines <= 1 or same)
            measures.append(
                _measure(
                    ctx,
                    f"wits:{market}:{year}",
                    market_iso3=market,
                    code=hs6,
                    hs6=hs6,
                    kind=TariffMeasureKind.MFN,
                    origin_kind=TariffOriginKind.ERGA_OMNES,
                    origin_code="*",
                    origin_group_id=None,
                    duty_text=(
                        f"{value:g}% (simple average of {lines} national lines)"
                        if value is not None
                        else "not reported"
                    ),
                    ad_valorem_pct=value,
                    specific_amount=None,
                    specific_unit=None,
                    is_compound=False,
                    is_resolved=resolved,
                    measure_ref=f"WITS:TRN:{year}",
                    legal_ref="WITS TRAINS, reported MFN (UNCTAD TRAINS)",
                    source_url="https://wits.worldbank.org/",
                    status=TariffStatus.IN_FORCE,
                    valid_from=dt.date(int(year), 1, 1),
                    valid_to=dt.date(int(year), 12, 31),
                    conditions={
                        "simple_average_of_lines": lines,
                        "min_rate": lo,
                        "max_rate": hi,
                        "nomenclature": obs.get("NOMENCODE"),
                    },
                )
            )
    out: list[Record] = list(measures)
    for year in sorted(years):
        scope = f"wits:{market}:{year}"
        out.append(
            _snapshot(ctx, market, scope, [m for m in measures if m.snapshot_scope == scope])
        )
    return out


# --- Federal Register ---------------------------------------------------------------------------

TRADE_AGENCIES = {
    "trade-representative-office-of-united-states",
    "international-trade-administration",
    "international-trade-commission",
    "u-s-customs-and-border-protection",
    "executive-office-of-the-president",
    "industry-and-security-bureau",
}
_HTS_REF = re.compile(r"\b\d{4}\.\d{2}(?:\.\d{2}(?:\.\d{2})?)?\b")


def notice_kind(title: str) -> TradeNoticeKind:
    t = title.lower()
    if "exclusion" in t:
        return TradeNoticeKind.EXCLUSION
    if re.search(
        r"modification|harmonized tariff schedule|additional (ad valorem )?dut|"
        r"reciprocal|section 301|section 232|imposing|tariff",
        t,
    ):
        return TradeNoticeKind.TARIFF_MODIFICATION
    if re.search(
        r"antidumping|anti-dumping|countervailing|less-than-fair-value|"
        r"less than fair value|determination|sunset review|safeguard",
        t,
    ):
        return TradeNoticeKind.TRADE_REMEDY
    return TradeNoticeKind.OTHER


def parse_federal_register(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = json.loads(body)
    out: list[Record] = []
    for r in doc.get("results", []):
        agencies = [a.get("slug") or a.get("name") or "" for a in r.get("agencies") or []]
        if not TRADE_AGENCIES & set(agencies):
            continue
        title = r.get("title") or ""
        text = " ".join(
            [
                title,
                r.get("abstract") or "",
                " ".join(r.get("excerpts") or [])
                if isinstance(r.get("excerpts"), list)
                else str(r.get("excerpts") or ""),
            ]
        )
        published = dt.date.fromisoformat(r["publication_date"])
        out.append(
            TradePolicyNoticeRecord(
                id=ctx.rid("trade_policy_notice", r["document_number"]),
                **ctx.lineage(
                    source_record_id=r["document_number"],
                    available_at=dt.datetime.combine(published, dt.time(), dt.UTC),
                ),
                market_iso3=USA,
                document_number=r["document_number"],
                title=title,
                doc_type=r.get("type"),
                kind=notice_kind(title),
                publication_date=published,
                effective_on=dt.date.fromisoformat(r["effective_on"])
                if r.get("effective_on")
                else None,
                url=r.get("html_url") or "",
                abstract=r.get("abstract"),
                agencies=agencies,
                countries=[c for c in countries_in(title) if c != USA],
                hts_refs=sorted(set(_HTS_REF.findall(_TAGS.sub(" ", text)))),
            )
        )
    return out


# --- EU preferences (manual table, DS-TRADE-08) -------------------------------------------------

EU_PREFS_SCOPE = "eu-prefs"


def _eu_ref(group: str, spec: dict[str, Any]) -> str:
    """'EU-GSP:*' or 'EU-GSP:*:in61,62,63' / ':ex93': stable under reordering of the table."""
    ref = f"{group}:{spec['code']}"
    if spec.get("include_chapters"):
        ref += ":in" + ",".join(spec["include_chapters"])
    if spec.get("exclude_chapters"):
        ref += ":ex" + ",".join(spec["exclude_chapters"])
    return ref


def eu_prefs_as_of(body: bytes) -> dt.datetime:
    as_of = yaml.safe_load(body)["as_of"]
    return dt.datetime.combine(as_of, dt.time(), dt.UTC)


def parse_eu_preferences(body: bytes, ctx: ParseContext) -> list[Record]:
    """The hand-kept EU preference table (config/tariffs/eu_preferences.yaml) → groups, members
    and measures. Rates relative to MFN or staged by an FTA stay unresolved (no number)."""
    doc = yaml.safe_load(body)
    if ctx.fetched_at is None:
        ctx = ParseContext(ctx.source_id, ctx.data_mode, fetched_at=eu_prefs_as_of(body))
    market = doc["market"]
    out: list[Record] = []
    measures: list[TariffMeasureRecord] = []
    for code, g in doc["groups"].items():
        recs = _group(ctx, market, code, g["name"], g.get("scheme"), [], g.get("legal_ref"))
        gid = recs[0].id
        out += recs
        for m in g.get("members", []):
            key = f"{market}|{code}|{m['iso3']}"
            out.append(
                TariffOriginMemberRecord(
                    id=ctx.rid("tariff_origin_member", key),
                    **ctx.lineage(source_record_id=key),
                    group_id=gid,
                    market_iso3=market,
                    group_code=code,
                    member_iso2=_countries().get(m["iso3"], {}).get("iso2"),
                    member_iso3=m["iso3"],
                    valid_from=m.get("valid_from"),
                    valid_to=m.get("valid_to"),
                )
            )
        for spec in g.get("measures", []):
            pct = spec.get("ad_valorem_pct")
            resolved = pct is not None and not spec.get("unresolved")
            conditions = {
                k: spec[k]
                for k in ("exclude_chapters", "include_chapters", "mfn_reduction_pct", "verify")
                if k in spec
            }
            measures.append(
                _measure(
                    ctx,
                    EU_PREFS_SCOPE,
                    market_iso3=market,
                    code=spec["code"],
                    hs6=None,
                    kind=TariffMeasureKind.PREFERENTIAL,
                    origin_kind=TariffOriginKind.GROUP,
                    origin_code=code,
                    origin_group_id=gid,
                    duty_text=spec["duty_text"],
                    ad_valorem_pct=float(pct) if pct is not None else None,
                    specific_amount=None,
                    specific_unit=None,
                    is_compound=False,
                    is_resolved=resolved,
                    # the rule's scope, not its list position: reordering is not a change
                    measure_ref=_eu_ref(code, spec),
                    legal_ref=g.get("legal_ref"),
                    source_url="https://ec.europa.eu/taxation_customs/dds2/taric/",
                    status=TariffStatus.IN_FORCE,
                    valid_from=None,
                    valid_to=None,
                    conditions=conditions,
                )
            )
    out += measures
    out.append(_snapshot(ctx, market, EU_PREFS_SCOPE, measures))
    return out
