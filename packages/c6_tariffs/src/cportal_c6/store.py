"""C6 on the database: current measures, change detection, precomputed effective rates.

`refresh()` is what the worker runs after a tariff source ingests (and daily):

1. `mark_current`: per (source, scope), the measures in the latest snapshot are current; the
   older versions stay as history with `is_current = false`.
2. `detect_changes`: consecutive snapshots of a scope with different content are diffed into
   `tariff_change` rows (deterministic ids: re-running writes nothing new).
3. `compute_rates`: the effective duty per market × HS6 × origin on a date, from the current
   measures, stored in `tariff_effective_rate` so API reads stay fast (AGENTS rule 7).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from itertools import pairwise
from typing import Any
from uuid import UUID

from cportal_core.enums import DataMode, TariffChangeKind, TariffMeasureKind
from cportal_core.ids import stable_id
from cportal_core.loader import upsert
from cportal_core.models import (
    OutboxEvent,
    TariffChange,
    TariffEffectiveRate,
    TariffMeasure,
    TariffOriginGroup,
    TariffOriginMember,
    TariffSnapshot,
)
from cportal_core.schemas.records import TariffChangeRecord, TariffEffectiveRateRecord
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from cportal_c6 import ENGINE_VERSION, SOURCE_ID, catalog
from cportal_c6.diff import Change, diff_measures
from cportal_c6.rates import Measure, Membership, RateResult, effective_rate

SNAPSHOTS_PER_SCOPE = 6  # pairs older than this were diffed by earlier refreshes


def to_measure(row: TariffMeasure) -> Measure:
    return Measure(
        id=str(row.id),
        market=row.market_iso3,
        code=row.code,
        hs6=row.hs6,
        kind=row.kind,
        origin_kind=row.origin_kind,
        origin_code=row.origin_code,
        duty_text=row.duty_text,
        ad_valorem_pct=row.ad_valorem_pct,
        is_resolved=row.is_resolved,
        measure_ref=row.measure_ref,
        legal_ref=row.legal_ref,
        source_id=row.source_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        conditions=row.conditions or {},
        content_hash=row.content_hash,
        source_url=row.source_url,
        data_mode=row.data_mode,
    )


def load_members(session: Session) -> Membership:
    out: Membership = defaultdict(list)
    rows = session.execute(
        select(
            TariffOriginMember.market_iso3,
            TariffOriginMember.group_code,
            TariffOriginMember.member_iso3,
            TariffOriginMember.valid_from,
            TariffOriginMember.valid_to,
        )
        .where(TariffOriginMember.member_iso3.is_not(None), ~TariffOriginMember.is_synthetic)
        .distinct()
    )
    for market, group, iso3, start, end in rows:
        out[(market, group)].append((str(iso3), start, end))
    return dict(out)


def load_current(session: Session, hs6s: Iterable[str] | None = None) -> list[Measure]:
    q = select(TariffMeasure).where(TariffMeasure.is_current, ~TariffMeasure.is_synthetic)
    if hs6s is not None:
        q = q.where(or_(TariffMeasure.hs6.in_(list(hs6s)), TariffMeasure.code == "*"))
    return [to_measure(r) for r in session.scalars(q)]


def _scopes(session: Session) -> list[tuple[str, str]]:
    rows = session.execute(select(TariffSnapshot.source_id, TariffSnapshot.scope).distinct())
    return sorted((str(s), str(c)) for s, c in rows)


def _latest(session: Session, source_id: str, scope: str, n: int) -> list[TariffSnapshot]:
    q = (
        select(TariffSnapshot)
        .where(TariffSnapshot.source_id == source_id, TariffSnapshot.scope == scope)
        .order_by(TariffSnapshot.fetched_at.desc())
        .limit(n)
    )
    return list(session.scalars(q))


def mark_current(session: Session) -> int:
    """Measures in the latest snapshot of their scope are current; others are history."""
    n = 0
    for source_id, scope in _scopes(session):
        (snap,) = _latest(session, source_id, scope, 1)
        ids = list(snap.measure_ids)
        session.execute(
            update(TariffMeasure)
            .where(TariffMeasure.source_id == source_id, TariffMeasure.snapshot_scope == scope)
            .values(is_current=TariffMeasure.id.in_(ids) if ids else False)
        )
        n += len(ids)
    return n


def _measures_by_id(session: Session, ids: Iterable[str]) -> list[Measure]:
    rows = session.scalars(select(TariffMeasure).where(TariffMeasure.id.in_(list(ids))))
    return [to_measure(r) for r in rows]


def _change_record(c: Change, prev: TariffSnapshot, new: TariffSnapshot) -> TariffChangeRecord:
    m = c.new or c.old
    assert m is not None
    key = "|".join(c.key)
    mode = DataMode.LIVE if new.data_mode == DataMode.LIVE.value else DataMode.REPLAY
    return TariffChangeRecord(
        id=stable_id("tariff_change", prev.id, new.id, key),
        source_id=new.source_id,
        source_record_id=key[:256],
        data_mode=mode,
        generator_version=ENGINE_VERSION,
        available_at=new.fetched_at,
        market_iso3=m.market,
        code=m.code,
        hs6=m.hs6,
        kind=TariffMeasureKind(m.kind),
        origin_code=m.origin_code,
        measure_ref=m.measure_ref,
        change=TariffChangeKind(c.change),
        old_measure_id=UUID(c.old.id) if c.old else None,
        new_measure_id=UUID(c.new.id) if c.new else None,
        old_duty_text=c.old.duty_text if c.old else None,
        new_duty_text=c.new.duty_text if c.new else None,
        old_ad_valorem_pct=c.old.ad_valorem_pct if c.old else None,
        new_ad_valorem_pct=c.new.ad_valorem_pct if c.new else None,
        delta_pp=c.delta_pp,
        old_status=c.old.status if c.old else None,
        new_status=c.new.status if c.new else None,
        effective_from=c.effective_from,
        detected_at=new.fetched_at,
        prev_snapshot_id=prev.id,
        new_snapshot_id=new.id,
        scope=new.scope,
    )


def detect_changes(session: Session) -> list[TariffChangeRecord]:
    """Diff consecutive snapshots of every scope; returns only changes not stored before."""
    records: list[TariffChangeRecord] = []
    for source_id, scope in _scopes(session):
        snaps = list(reversed(_latest(session, source_id, scope, SNAPSHOTS_PER_SCOPE)))
        for prev, new in pairwise(snaps):
            if prev.content_hash == new.content_hash:
                continue
            if prev.generator_version != new.generator_version:
                continue  # a parser upgrade re-baselines; it is not a tariff change (A-133)
            old = _measures_by_id(session, prev.measure_ids)
            cur = _measures_by_id(session, new.measure_ids)
            records += [_change_record(c, prev, new) for c in diff_measures(old, cur)]
    if not records:
        return []
    known = set(
        session.scalars(select(TariffChange.id).where(TariffChange.id.in_([r.id for r in records])))
    )
    fresh = [r for r in records if r.id not in known]
    if fresh:
        upsert(session, fresh)
    return fresh


def _lines(ms: list[Measure], market: str, hs6: str) -> tuple[list[str], list[Measure]]:
    """National lines of one HS6 product and the line-level measures to use: the market's
    live schedule when it has this product, else the newest reported MFN (WITS)."""
    here = [m for m in ms if m.market == market and m.hs6 == hs6 and m.code != "*"]
    live = catalog.live_source(market)
    chosen = [m for m in here if m.source_id == live] if live else []
    if not chosen:
        chosen = [m for m in here if m.source_id == catalog.MFN_HISTORY]
    lines = sorted({m.code for m in chosen if m.kind == "mfn" and m.origin_kind == "erga_omnes"})
    return lines, chosen


def rate_cell(
    ms: list[Measure], members: Membership, market: str, hs6: str, origin: str, on: dt.date
) -> tuple[list[RateResult], list[Measure]]:
    lines, line_measures = _lines(ms, market, hs6)
    wide = [m for m in ms if m.market == market and m.code == "*"]
    pool = line_measures + wide
    return [effective_rate(pool, members, market, line, origin, on) for line in lines], pool


def _cell_record(
    results: list[RateResult],
    pool: list[Measure],
    market: str,
    hs6: str,
    origin: str,
    on: dt.date,
    now: dt.datetime,
) -> TariffEffectiveRateRecord:
    resolved = [r for r in results if r.is_resolved and r.effective_pct is not None]
    pcts = [r.effective_pct for r in resolved if r.effective_pct is not None]
    # representative line: the highest resolved duty (worst case), else the first line
    rep = (
        max(resolved, key=lambda r: r.effective_pct or 0.0)
        if resolved
        else (results[0] if results else None)
    )
    used = {c.source_id for r in results for c in r.components}
    modes = {m.data_mode for m in pool if m.source_id in used}
    notes = sorted({n for r in results for n in r.notes})
    if not results:
        notes = ["no tariff line found for this product in this market"]
    return TariffEffectiveRateRecord(
        id=stable_id("tariff_effective_rate", on, market, hs6, origin),
        source_id=SOURCE_ID,
        source_record_id=f"{on}|{market}|{hs6}|{origin}",
        data_mode=DataMode.LIVE if DataMode.LIVE.value in modes else DataMode.REPLAY,
        generator_version=ENGINE_VERSION,
        available_at=now,
        as_of=on,
        market_iso3=market,
        hs6=hs6,
        origin_iso3=origin,
        effective_pct_min=min(pcts) if pcts else None,
        effective_pct_max=max(pcts) if pcts else None,
        is_resolved=bool(results) and len(resolved) == len(results),
        n_lines=len(results),
        base_pct=rep.base_pct if rep else None,
        preference_pct=rep.preference_pct if rep else None,
        additional_pct=rep.additional_pct if rep else None,
        is_stale=any(r.is_stale for r in results),
        components=[c.as_dict() for c in rep.components] if rep else [],
        lines=[
            {"code": r.line_code, "effective_pct": r.effective_pct, "is_resolved": r.is_resolved}
            for r in results
        ],
        notes=notes,
        sources=sorted(used),
        computed_at=now,
    )


def compute_rates(
    session: Session,
    on: dt.date,
    hs6s: list[str] | None = None,
    markets: list[str] | None = None,
    origins: list[str] | None = None,
) -> list[TariffEffectiveRateRecord]:
    hs6s = hs6s or [p.hs6 for p in catalog.products()]
    markets = markets or list(catalog.markets())
    origins = origins or catalog.origins()
    ms = load_current(session, hs6s)
    members = load_members(session)
    now = dt.datetime.now(dt.UTC)
    out: list[TariffEffectiveRateRecord] = []
    for market in markets:
        for hs6 in hs6s:
            for origin in origins:
                results, pool = rate_cell(ms, members, market, hs6, origin, on)
                out.append(_cell_record(results, pool, market, hs6, origin, on, now))
    return out


def write_rates(session: Session, on: dt.date, records: list[TariffEffectiveRateRecord]) -> int:
    session.execute(delete(TariffEffectiveRate).where(TariffEffectiveRate.as_of == on))
    upsert(session, records)
    return len(records)


def refresh(session: Session, on: dt.date | None = None) -> dict[str, Any]:
    """Current flags → changes → effective rates for `on` (default: today, UTC)."""
    on = on or dt.datetime.now(dt.UTC).date()
    current = mark_current(session)
    session.flush()
    fresh = detect_changes(session)
    rates = write_rates(session, on, compute_rates(session, on))
    if fresh:
        session.add(
            OutboxEvent(
                topic="tariff.changed",
                payload={
                    "changes": len(fresh),
                    "markets": sorted({c.market_iso3 for c in fresh}),
                    "ids": [str(c.id) for c in fresh[:50]],
                },
            )
        )
    groups = session.scalar(select(TariffOriginGroup.id).limit(1)) is not None
    return {
        "current_measures": current,
        "new_changes": len(fresh),
        "rates": rates,
        "as_of": on.isoformat(),
        "has_groups": groups,
    }
