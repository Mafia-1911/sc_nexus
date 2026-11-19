"""C6 read API (what `apps/api` calls). Tariffs are real data only: no scenario rows exist.

Reads use the precomputed `tariff_effective_rate` rows; a date that was not precomputed (e.g.
"as of the LDC transition end") is computed on the fly from the current measures, which is
bounded (≈ 0.3 s for the whole matrix) and never written by a request.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any
from uuid import UUID

from cportal_core.models import (
    TariffChange,
    TariffEffectiveRate,
    TariffMeasure,
    TariffNews,
    TariffNomenclature,
    TariffOriginGroup,
    TariffOriginMember,
    TariffSnapshot,
    TradePolicyNotice,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cportal_c6 import catalog, diff, store
from cportal_c6.rates import Membership, _member
from cportal_c6.schemas import (
    CellOut,
    ChangeOut,
    ComponentOut,
    FeedOut,
    LineRateOut,
    MarketDetailOut,
    MarketOut,
    MatrixOut,
    NewsConfirmationOut,
    NewsOut,
    NoticeOut,
    OriginDetailOut,
    OriginOut,
    OverviewOut,
    ProductDetailOut,
    ProductOut,
    SchemeOut,
)


def _origin(iso3: str) -> OriginOut:
    return OriginOut(iso3=iso3, name=catalog.country_names().get(iso3, iso3))


def latest_as_of(session: Session) -> dt.date | None:
    return session.scalar(select(func.max(TariffEffectiveRate.as_of)))


def overview(session: Session, now: dt.datetime | None = None) -> OverviewOut:
    now = now or dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(days=30)
    markets: list[MarketOut] = []
    counts = dict(
        session.execute(
            select(TariffMeasure.market_iso3, func.count())
            .where(TariffMeasure.is_current)
            .group_by(TariffMeasure.market_iso3)
        ).all()
    )
    wits_to = dict(
        session.execute(
            select(TariffMeasure.market_iso3, func.max(TariffMeasure.valid_to))
            .where(TariffMeasure.is_current, TariffMeasure.source_id == catalog.MFN_HISTORY)
            .group_by(TariffMeasure.market_iso3)
        ).all()
    )
    for code, m in catalog.markets().items():
        live = catalog.live_source(code)
        last = session.execute(
            select(TariffSnapshot.fetched_at, TariffSnapshot.data_mode)
            .where(TariffSnapshot.market_iso3 == code)
            .order_by(TariffSnapshot.fetched_at.desc())
            .limit(1)
        ).first()
        markets.append(
            MarketOut(
                code=code,
                name=m["name"],
                live_source=live,
                last_fetched_at=last[0] if last else None,
                data_mode=last[1] if last else None,
                current_measures=int(counts.get(code, 0)),
                mfn_year=wits_to[code].year if wits_to.get(code) else None,
            )
        )
    return OverviewOut(
        as_of=latest_as_of(session),
        markets=markets,
        origins=[_origin(o) for o in catalog.origins()],
        products=[
            ProductOut(hs6=p.hs6, name=p.name, industry=p.industry, key=p.key)
            for p in catalog.products()
        ],
        feeds=[FeedOut.model_validate(f) for f in catalog.feeds()],
        changes_30d=session.scalar(
            select(func.count()).select_from(TariffChange).where(TariffChange.detected_at >= since)
        )
        or 0,
        notices_30d=session.scalar(
            select(func.count())
            .select_from(TradePolicyNotice)
            .where(TradePolicyNotice.publication_date >= since.date())
        )
        or 0,
        latest_change_at=session.scalar(select(func.max(TariffChange.detected_at))),
        news_30d=session.scalar(
            select(func.count())
            .select_from(TariffNews)
            .where(*_news_scope(), TariffNews.last_published >= since)
        )
        or 0,
    )


def _cells(rows: list[Any]) -> tuple[list[CellOut], list[str]]:
    """Cells with their notes moved to one shared list (each note text sent once)."""
    index: dict[str, int] = {}
    cells: list[CellOut] = []
    for r in rows:
        ids = [index.setdefault(n, len(index)) for n in r.notes]
        cells.append(
            CellOut(
                market=r.market_iso3,
                hs6=r.hs6,
                origin=r.origin_iso3,
                effective_pct_min=r.effective_pct_min,
                effective_pct_max=r.effective_pct_max,
                is_resolved=r.is_resolved,
                is_stale=r.is_stale,
                is_ceiling=r.is_ceiling,
                lower_pct=r.lower_pct,
                upper_pct=r.upper_pct,
                base_pct=r.base_pct,
                preference_pct=r.preference_pct,
                additional_pct=r.additional_pct,
                n_lines=r.n_lines,
                note_ids=ids,
                sources=list(r.sources),
                data_mode=str(r.data_mode),
            )
        )
    return cells, list(index)


# The matrix never needs a cell's breakdown (components, lines): skip those JSON columns.
_MATRIX_COLUMNS = (
    TariffEffectiveRate.market_iso3, TariffEffectiveRate.hs6, TariffEffectiveRate.origin_iso3,
    TariffEffectiveRate.effective_pct_min, TariffEffectiveRate.effective_pct_max,
    TariffEffectiveRate.is_resolved, TariffEffectiveRate.is_stale, TariffEffectiveRate.base_pct,
    TariffEffectiveRate.preference_pct, TariffEffectiveRate.additional_pct,
    TariffEffectiveRate.n_lines, TariffEffectiveRate.notes, TariffEffectiveRate.is_ceiling,
    TariffEffectiveRate.lower_pct, TariffEffectiveRate.upper_pct,
    TariffEffectiveRate.sources,
    TariffEffectiveRate.data_mode,
)  # fmt: skip


def matrix(
    session: Session,
    as_of: dt.date | None = None,
    hs6: list[str] | None = None,
    markets: list[str] | None = None,
    origins: list[str] | None = None,
    industry: str | None = None,
) -> MatrixOut:
    if industry:
        allowed = {p.hs6 for p in catalog.products() if p.industry == industry}
        hs6 = sorted(h for h in (hs6 or allowed) if h in allowed)
        if not hs6:  # nothing in this industry matches: an empty matrix, never all of it
            return MatrixOut(
                as_of=as_of or latest_as_of(session) or dt.datetime.now(dt.UTC).date(),
                precomputed=False, notes=[], cells=[],
            )  # fmt: skip
    stored = latest_as_of(session) if as_of is None else as_of
    if stored is not None:
        q = select(*_MATRIX_COLUMNS).where(TariffEffectiveRate.as_of == stored)
        if hs6:
            q = q.where(TariffEffectiveRate.hs6.in_(hs6))
        if markets:
            q = q.where(TariffEffectiveRate.market_iso3.in_(markets))
        if origins:
            q = q.where(TariffEffectiveRate.origin_iso3.in_(origins))
        q = q.order_by(
            TariffEffectiveRate.market_iso3,
            TariffEffectiveRate.hs6,
            TariffEffectiveRate.origin_iso3,
        )
        rows = list(session.execute(q))
        if rows:
            cells, notes = _cells(rows)
            return MatrixOut(as_of=stored, precomputed=True, notes=notes, cells=cells)
    on = as_of or dt.datetime.now(dt.UTC).date()
    cells, notes = _cells(store.compute_rates(session, on, hs6, markets, origins))
    return MatrixOut(as_of=on, precomputed=False, notes=notes, cells=cells)


def _change(c: TariffChange) -> ChangeOut:
    return ChangeOut(
        id=str(c.id),
        market=c.market_iso3,
        code=c.code,
        hs6=c.hs6,
        kind=c.kind,
        origin_code=c.origin_code,
        measure_ref=c.measure_ref,
        change=c.change,
        old_duty_text=c.old_duty_text,
        new_duty_text=c.new_duty_text,
        old_pct=c.old_ad_valorem_pct,
        new_pct=c.new_ad_valorem_pct,
        delta_pp=c.delta_pp,
        old_status=c.old_status,
        new_status=c.new_status,
        effective_from=c.effective_from,
        detected_at=c.detected_at,
        source_id=c.source_id,
        data_mode=c.data_mode,
    )


def changes(
    session: Session,
    market: str | None = None,
    origin: str | None = None,
    hs6: str | None = None,
    since: dt.datetime | None = None,
    limit: int = 50,
) -> list[ChangeOut]:
    q = select(TariffChange)
    if market:
        q = q.where(TariffChange.market_iso3 == market)
    if origin:
        q = q.where(or_(TariffChange.origin_code == origin, TariffChange.origin_code == "*"))
    if hs6:
        q = q.where(or_(TariffChange.hs6 == hs6, TariffChange.code == "*"))
    if since:
        q = q.where(TariffChange.detected_at >= since)
    q = q.order_by(TariffChange.detected_at.desc(), TariffChange.measure_ref).limit(limit)
    return [_change(c) for c in session.scalars(q)]


def notices(
    session: Session, kind: str | None = None, country: str | None = None, limit: int = 50
) -> list[NoticeOut]:
    q = select(TradePolicyNotice)
    if kind:
        q = q.where(TradePolicyNotice.kind == kind)
    if country:
        q = q.where(TradePolicyNotice.countries.contains([country]))
    q = q.order_by(
        TradePolicyNotice.publication_date.desc(), TradePolicyNotice.document_number.desc()
    ).limit(limit)
    return [
        NoticeOut(
            document_number=n.document_number,
            title=n.title,
            kind=n.kind,
            doc_type=n.doc_type,
            publication_date=n.publication_date,
            effective_on=n.effective_on,
            url=n.url,
            agencies=list(n.agencies),
            countries=list(n.countries),
            hts_refs=list(n.hts_refs),
            data_mode=n.data_mode,
        )
        for n in session.scalars(q)
    ]


def product(
    session: Session,
    hs6: str,
    as_of: dt.date | None = None,
    markets: list[str] | None = None,
    origins: list[str] | None = None,
) -> ProductDetailOut | None:
    prod = next((p for p in catalog.products() if p.hs6 == hs6), None)
    if prod is None:
        return None
    on = as_of or dt.datetime.now(dt.UTC).date()
    origins = origins or catalog.origins()
    ms = store.load_current(session, [hs6])
    members = store.load_members(session)
    descriptions = {
        (m, c): d
        for m, c, d in session.execute(
            select(
                TariffNomenclature.market_iso3,
                TariffNomenclature.code,
                TariffNomenclature.description,
            ).where(TariffNomenclature.hs6 == hs6)
        )
    }
    group_names = {
        (m, g): n
        for m, g, n in session.execute(
            select(
                TariffOriginGroup.market_iso3, TariffOriginGroup.group_code, TariffOriginGroup.name
            )
        )
    }
    countries = catalog.country_names()

    def origin_name(market: str, code: str) -> str:
        if code == "*":
            return "All origins"
        return group_names.get((market, code)) or countries.get(code, code)

    out: list[MarketDetailOut] = []
    used: set[str] = set()
    for market in markets or list(catalog.markets()):
        lines: list[LineRateOut] = []
        for origin in origins:
            results, _ = store.rate_cell(ms, members, market, hs6, origin, on)
            used |= {m for r in results for m in r.sources}
            for r in results:
                lines.append(
                    LineRateOut(
                        code=r.line_code,
                        description=descriptions.get((market, r.line_code)),
                        origin=origin,
                        effective_pct=r.effective_pct,
                        is_resolved=r.is_resolved,
                        is_stale=r.is_stale,
                        base_pct=r.base_pct,
                        preference_pct=r.preference_pct,
                        additional_pct=r.additional_pct,
                        lower_pct=r.lower_pct,
                        upper_pct=r.upper_pct,
                        components=[
                            ComponentOut(
                                **c.__dict__, origin_name=origin_name(market, c.origin_code)
                            )
                            for c in r.components
                        ],
                        notes=r.notes,
                    )
                )
        out.append(
            MarketDetailOut(
                market=market,
                lines=lines,
                changes=changes(session, market=market, hs6=hs6, limit=20),
            )
        )
    modes = Counter(m.data_mode for m in ms if m.source_id in used)
    return ProductDetailOut(
        product=ProductOut(hs6=prod.hs6, name=prod.name, industry=prod.industry),
        as_of=on,
        origins=origins,
        markets=out,
        sources=sorted(used),
        data_modes=dict(modes),
    )


def origin_detail(session: Session, iso3: str, on: dt.date | None = None) -> OriginDetailOut:
    """Which schemes and FTAs cover a country in each market, and its country surcharges."""
    on = on or dt.datetime.now(dt.UTC).date()
    rows = session.execute(
        select(
            TariffOriginMember.market_iso3,
            TariffOriginMember.group_code,
            TariffOriginGroup.name,
            TariffOriginGroup.scheme,
            TariffOriginMember.valid_from,
            TariffOriginMember.valid_to,
            TariffOriginGroup.source_id,
            TariffOriginMember.data_mode,
        )
        .join(TariffOriginGroup, TariffOriginGroup.id == TariffOriginMember.group_id)
        .where(
            TariffOriginMember.member_iso3 == iso3,
            or_(TariffOriginMember.valid_from.is_(None), TariffOriginMember.valid_from <= on),
            or_(TariffOriginMember.valid_to.is_(None), TariffOriginMember.valid_to >= on),
        )
        .distinct()
    ).all()
    modes: Counter[str] = Counter(str(r[-1]) for r in rows)
    schemes = [
        SchemeOut(market=m, group_code=g, name=n, scheme=s, valid_from=f, valid_to=t, source_id=src)
        for m, g, n, s, f, t, src in sorted(r[:-1] for r in rows)
    ]
    surcharges = session.scalars(
        select(TariffMeasure)
        .where(
            TariffMeasure.is_current,
            TariffMeasure.origin_kind == "country",
            TariffMeasure.origin_code == iso3,
            TariffMeasure.code == "*",
            TariffMeasure.status != "terminated",
            or_(TariffMeasure.valid_from.is_(None), TariffMeasure.valid_from <= on),
            or_(TariffMeasure.valid_to.is_(None), TariffMeasure.valid_to >= on),
        )
        .order_by(TariffMeasure.market_iso3, TariffMeasure.measure_ref)
    )
    out: list[dict[str, Any]] = []
    for m in surcharges:
        modes[str(m.data_mode)] += 1
        out.append(
            {
                "market": m.market_iso3,
                "measure_ref": m.measure_ref,
                "kind": m.kind,
                "duty_text": m.duty_text,
                "pct": m.ad_valorem_pct,
                "status": m.status,
                "valid_from": m.valid_from,
                "valid_to": m.valid_to,
                "legal_ref": m.legal_ref,
                "source_url": m.source_url,
                "is_resolved": m.is_resolved,
                "source_id": m.source_id,
            }
        )
    return OriginDetailOut(
        origin=_origin(iso3), schemes=schemes, surcharges=out, data_modes=dict(modes)
    )


# --- tariff news (C2 trade-policy events with their tariff signal, Q-25) -----------------------

NEWS_DAYS = 60
CONFIRM_BEFORE = dt.timedelta(days=30)  # a schedule may change a little before the story
CONFIRM_AFTER = dt.timedelta(days=90)  # or a while after it is announced
_LABEL = {True: "in the schedule", False: "announced, not in the schedule yet"}


def _news_scope() -> list[Any]:
    """Real tariff news only (C2 writes stories from real articles; scenarios have none)."""
    return [~TariffNews.is_synthetic, TariffNews.scenario_id.is_(None)]


def _agrees(direction: str, change: TariffChange) -> bool:
    does = diff.direction(change.kind, change.origin_code, change.change, change.delta_pp)
    if direction == "exempt":
        return does in ("exempt", "cut")
    return direction in ("raise", "cut") and does == direction


def _industry_hs6() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in catalog.products():
        out.setdefault(p.industry, set()).add(p.hs6)
    return out


def _in_group(members: Membership | None, c: TariffChange, origins: set[str], on: dt.date) -> bool:
    return any(_member(members or {}, c.market_iso3, c.origin_code, o, on) for o in origins)


def _confirmation(
    changes: list[TariffChange],
    signal: dict[str, Any],
    published: dt.datetime,
    members: Membership | None = None,
) -> TariffChange | None:
    """The schedule change that confirms a story: same market, an origin it names (directly, as
    a member of the change's group on the story's date, or a change for every origin), a product
    of an industry it names (or a country-wide change), the same direction, detected within the
    window around the story."""
    markets = set(signal.get("markets") or [])
    origins = set(signal.get("origins") or [])
    hs6s = set().union(*(_industry_hs6().get(i, set()) for i in signal.get("industries") or []))
    on = published.date()
    for c in changes:  # newest first
        if c.market_iso3 not in markets:
            continue
        named = c.origin_code == "*" or c.origin_code in origins
        if origins and not named and not _in_group(members, c, origins, on):
            continue
        if hs6s and c.code != "*" and c.hs6 is not None and c.hs6 not in hs6s:
            continue  # a change on another product does not confirm this story
        if not (published - CONFIRM_BEFORE <= c.detected_at <= published + CONFIRM_AFTER):
            continue
        if _agrees(str(signal.get("direction")), c):
            return c
    return None


def news(
    session: Session,
    market: str | None = None,
    origin: str | None = None,
    limit: int = 50,
    now: dt.datetime | None = None,
    event_id: UUID | None = None,
) -> list[NewsOut]:
    """Tariff news stories (C2, from RSS and GDELT), newest first, each with whether the official
    schedule already shows the move."""
    now = now or dt.datetime.now(dt.UTC)
    q = select(TariffNews).where(*_news_scope())
    if event_id is not None:  # the story behind one disruption event (the Radar's drawer)
        q = q.where(TariffNews.event_id == event_id)
    else:
        q = q.where(TariffNews.last_published >= now - dt.timedelta(NEWS_DAYS))
    if market:
        q = q.where(TariffNews.markets.contains([market]))
    if origin:
        q = q.where(TariffNews.origins.contains([origin]))
    rows = list(session.scalars(q.order_by(TariffNews.first_published.desc()).limit(limit)))
    if not rows:
        return []
    # only the changes that could confirm one of these stories: their markets and time window
    first = min(n.first_published for n in rows) - CONFIRM_BEFORE
    last = max(n.first_published for n in rows) + CONFIRM_AFTER
    markets = sorted({m for n in rows for m in n.markets})
    changes = list(
        session.scalars(
            select(TariffChange)
            .where(
                TariffChange.market_iso3.in_(markets),
                TariffChange.detected_at >= first,
                TariffChange.detected_at <= last,
            )
            .order_by(TariffChange.detected_at.desc())
        )
    )
    members = store.load_members(session) if changes else {}
    out: list[NewsOut] = []
    for n in rows:
        signal = {
            "markets": n.markets,
            "origins": n.origins,
            "direction": n.direction,
            "industries": n.industries,
        }
        hit = _confirmation(changes, signal, n.first_published, members)
        out.append(
            NewsOut(
                id=str(n.id),
                event_id=str(n.event_id) if n.event_id else None,
                title=n.title,
                url=n.url,
                published=n.first_published,
                last_updated=n.last_published,
                reports=n.reports,
                outlets=list(n.outlets),
                source_id=n.source_id,
                direction=n.direction,
                status=n.status,
                markets=list(n.markets),
                origins=list(n.origins),
                rate_pct=n.rate_pct,
                previous_pct=n.previous_pct,
                industries=list(n.industries),
                effective=n.effective,
                quote=n.quote,
                confirmed=hit is not None,
                label=_LABEL[hit is not None],
                confirmation=None
                if hit is None
                else NewsConfirmationOut(
                    change_id=str(hit.id),
                    market=hit.market_iso3,
                    measure_ref=hit.measure_ref,
                    origin_code=hit.origin_code,
                    old_duty_text=hit.old_duty_text,
                    new_duty_text=hit.new_duty_text,
                    delta_pp=hit.delta_pp,
                    detected_at=hit.detected_at,
                ),
                data_mode=n.data_mode,
            )
        )
    return out
