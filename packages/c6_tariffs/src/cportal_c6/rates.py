"""Effective duty for one national tariff line, one origin, one date (pure, no database).

Rules (each has a unit test in tests/test_rates.py):

1. Base = the most specific MFN measure for every origin (longest code, latest start), or the
   column-2 rate when the origin is in a column-2 group (US). If no MFN measure is valid on the
   date, the newest earlier one is used and the result is flagged stale (WITS is annual).
2. Preferences (an FTA, GSP/EBA, DCTS, or an MFN rate for a specific group) replace the base for
   members on the date; the lowest resolved one wins, assuming the rules of origin are met
   (said in the notes). Relative preferences ("MFN minus 20 %") are computed from the base.
   Partially eligible lines (US "E*") are listed but not applied.
3. Additional duties for the origin (US Chapter 99, UK additional duties) add to that.
4. Exemptions, quotas, suspensions and trade remedies are listed, never applied: their
   conditions are not machine-readable here.
5. Anything not a plain ad valorem percentage makes the result unresolved (no number), with the
   verbatim duty text in the components. Nothing is guessed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# (market, group_code) → [(member ISO3, valid_from, valid_to)]
Membership = dict[tuple[str, str], list[tuple[str, dt.date | None, dt.date | None]]]


@dataclass(frozen=True)
class Measure:
    id: str
    market: str
    code: str
    hs6: str | None
    kind: str
    origin_kind: str
    origin_code: str
    duty_text: str
    ad_valorem_pct: float | None
    is_resolved: bool
    measure_ref: str
    legal_ref: str | None
    source_id: str
    status: str
    valid_from: dt.date | None
    valid_to: dt.date | None
    conditions: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    source_url: str | None = None
    data_mode: str = "replay"


@dataclass(frozen=True)
class Component:
    role: str  # base | preference | additional | possible_exemption | not_applied | unresolved
    measure_ref: str
    kind: str
    origin_code: str
    duty_text: str
    pct: float | None
    legal_ref: str | None
    source_id: str
    source_url: str | None
    valid_from: dt.date | None
    valid_to: dt.date | None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        for k in ("valid_from", "valid_to"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class RateResult:
    market: str
    line_code: str
    origin: str
    on: dt.date
    effective_pct: float | None = None
    is_resolved: bool = False
    base_pct: float | None = None
    preference_pct: float | None = None
    additional_pct: float | None = None
    is_stale: bool = False
    components: list[Component] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        return sorted({c.source_id for c in self.components})


NOT_APPLIED = {
    "quota": "inside a tariff-rate quota only",
    "suspension": "conditional relief",
    "trade_remedy": "trade remedy on specific goods or firms",
}


def _in_force(m: Measure, on: dt.date) -> bool:
    if m.status == "terminated":
        return False
    if m.valid_from and m.valid_from > on:
        return False
    return not (m.valid_to and m.valid_to < on)


def _code_applies(m: Measure, line_code: str) -> bool:
    if m.code != "*":
        return line_code.startswith(m.code)
    chapter = line_code[:2]
    include = m.conditions.get("include_chapters")
    exclude = m.conditions.get("exclude_chapters") or []
    return chapter not in exclude and (include is None or chapter in include)


def _member(members: Membership, market: str, group: str, origin: str, on: dt.date) -> bool:
    for iso3, start, end in members.get((market, group), []):
        if iso3 == origin and (start is None or start <= on) and (end is None or end >= on):
            return True
    return False


def _origin_applies(m: Measure, origin: str, members: Membership, on: dt.date) -> bool:
    if m.origin_kind == "erga_omnes":
        return True
    if m.origin_kind == "country":
        return m.origin_code == origin
    return _member(members, m.market, m.origin_code, origin, on)


def _component(m: Measure, role: str, pct: float | None, note: str = "") -> Component:
    return Component(
        role,
        m.measure_ref,
        m.kind,
        m.origin_code,
        m.duty_text,
        pct,
        m.legal_ref,
        m.source_id,
        m.source_url,
        m.valid_from,
        m.valid_to,
        note,
    )


def _specific_first(ms: list[Measure]) -> Measure:
    return max(
        ms,
        key=lambda m: (
            len(m.code) if m.code != "*" else 0,
            m.valid_from or dt.date.min,
            m.measure_ref,
        ),
    )


def _base(
    ms: list[Measure], origin: str, members: Membership, on: dt.date, r: RateResult
) -> Measure | None:
    col2 = [
        m
        for m in ms
        if m.kind == "column2"
        and m.origin_kind != "erga_omnes"
        and _in_force(m, on)
        and _origin_applies(m, origin, members, on)
    ]
    if col2:
        r.notes.append("column 2 rate: no normal trade relations with this origin")
        return _specific_first(col2)
    mfn = [m for m in ms if m.kind == "mfn" and m.origin_kind == "erga_omnes"]
    valid = [m for m in mfn if _in_force(m, on)]
    if valid:
        return _specific_first(valid)
    earlier = [m for m in mfn if m.status != "terminated" and m.valid_to and m.valid_to < on]
    if earlier:
        latest = max(earlier, key=lambda m: (m.valid_to or dt.date.min, len(m.code)))
        r.is_stale = True
        year = latest.valid_to.year if latest.valid_to else "?"
        r.notes.append(f"latest reported MFN rate is for {year} ({latest.source_id})")
        return latest
    return None


def effective_rate(
    measures: list[Measure],
    members: Membership,
    market: str,
    line_code: str,
    origin: str,
    on: dt.date,
) -> RateResult:
    r = RateResult(market, line_code, origin, on)
    ms = [m for m in measures if m.market == market and _code_applies(m, line_code)]
    base = _base(ms, origin, members, on, r)
    if base is None:
        r.notes.append("no MFN rate found for this line")
        return r
    r.base_pct = base.ad_valorem_pct if base.is_resolved else None
    if not base.is_resolved and base.conditions.get("max_rate") is not None:
        c = base.conditions
        r.notes.append(
            f"MFN differs across {c.get('simple_average_of_lines')} national lines: "
            f"{c.get('min_rate')}–{c.get('max_rate')} % (average {base.ad_valorem_pct:g} %)"
        )
    r.components.append(_component(base, "base", r.base_pct))
    resolved = base.is_resolved and base.ad_valorem_pct is not None

    best: tuple[float, Measure] | None = None
    unresolved_pref = False
    for m in ms:
        is_pref = m.kind == "preferential" or (m.kind == "mfn" and m.origin_kind != "erga_omnes")
        if not is_pref or not _in_force(m, on) or not _origin_applies(m, origin, members, on):
            continue
        if m.conditions.get("partial_eligibility"):
            r.components.append(
                _component(
                    m, "not_applied", m.ad_valorem_pct, "only some articles of this line qualify"
                )
            )
            continue
        pct = m.ad_valorem_pct if m.is_resolved else None
        if (
            pct is None
            and m.conditions.get("mfn_reduction_pct") is not None
            and r.base_pct is not None
        ):
            pct = round(r.base_pct * (1 - float(m.conditions["mfn_reduction_pct"]) / 100), 4)
        if pct is None:
            unresolved_pref = True
            r.components.append(
                _component(m, "unresolved", None, "preference not machine-readable")
            )
            continue
        if best is None or pct < best[0]:
            best = (pct, m)
    if best is not None and r.base_pct is not None and best[0] < r.base_pct:
        r.preference_pct = best[0]
        r.components.append(_component(best[1], "preference", best[0]))
        r.notes.append("preference assumes the rules of origin are met")
    if (
        unresolved_pref
        and (r.preference_pct if r.preference_pct is not None else r.base_pct or 0) > 0
    ):
        resolved = False
        r.notes.append("a preference for this origin could not be read as a number: see legal text")

    additional = 0.0
    category_exemptions: list[Measure] = []
    for m in ms:
        if not _in_force(m, on) or not _origin_applies(m, origin, members, on):
            continue
        if m.kind == "additional":
            if m.is_resolved and m.ad_valorem_pct is not None:
                additional += m.ad_valorem_pct
                r.components.append(_component(m, "additional", m.ad_valorem_pct))
            else:
                resolved = False
                r.components.append(_component(m, "unresolved", None, "additional duty"))
        elif m.kind == "exemption" and m.conditions.get("category"):
            # a product-category exemption whose HS list is in a legal note: if any surcharge
            # applies, it may not apply to this product, so no number is stated
            category_exemptions.append(m)
            r.components.append(
                _component(m, "possible_exemption", None, f"category: {m.conditions['category']}")
            )
        elif m.kind == "exemption":
            r.components.append(
                _component(
                    m, "possible_exemption", None, "may remove an additional duty: see legal text"
                )
            )
        elif m.kind in NOT_APPLIED and m.origin_kind != "erga_omnes":
            r.components.append(_component(m, "not_applied", m.ad_valorem_pct, NOT_APPLIED[m.kind]))
    surcharges = [c for c in r.components if c.role == "additional"]
    r.additional_pct = additional if surcharges else None
    if surcharges and category_exemptions:
        resolved = False
        for ex in category_exemptions:
            note = ex.conditions.get("note", "")
            ref = ex.conditions.get("note_ref", "")
            r.notes.append(
                f"surcharges may not apply: {ex.measure_ref} exempts {ex.conditions['category']}"
                f" ({note}{ref}); check whether this product is listed"
            )
    if len(surcharges) > 1:
        # Several surcharges for one origin: whether they stack or one supersedes another is
        # in the legal notes, not in the line texts. Show them all; do not add them up.
        resolved = False
        if r.base_pct is not None:
            start = r.preference_pct if r.preference_pct is not None else r.base_pct
            refs = ", ".join(c.measure_ref for c in surcharges)
            r.notes.append(
                f"{len(surcharges)} surcharges apply to this origin ({refs}); "
                f"if they all stack: {start + additional:g} %. See legal text"
            )

    if resolved and r.base_pct is not None:
        start = r.preference_pct if r.preference_pct is not None else r.base_pct
        r.effective_pct = round(start + additional, 4)
        r.is_resolved = True
    return r
