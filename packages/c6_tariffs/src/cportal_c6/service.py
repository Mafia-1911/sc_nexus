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
    Article,
    DisruptionEvent,
    EventMention,
    TariffChange,
    TariffEffectiveRate,
    TariffMeasure,
    TariffNomenclature,
    TariffOriginGroup,
    TariffOriginMember,
    TariffSnapshot,
    TradePolicyNotice,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cportal_c6 import catalog, store
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
            )
        )
    return OverviewOut(
        as_of=latest_as_of(session),
        markets=markets,
        origins=[_origin(o) for o in catalog.origins()],
        products=[
            ProductOut(hs6=p.hs6, name=p.name, industry=p.industry) for p in catalog.products()
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
            .select_from(DisruptionEvent)
            .where(*_news_scope(), DisruptionEvent.last_updated >= since)
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
    TariffEffectiveRate.n_lines, TariffEffectiveRate.notes, TariffEffectiveRate.sources,
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
        hs6 = [h for h in (hs6 or allowed) if h in allowed]
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
                        components=[ComponentOut(**c.__dict__) for c in r.components],
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
        )
        .join(TariffOriginGroup, TariffOriginGroup.id == TariffOriginMember.group_id)
        .where(TariffOriginMember.member_iso3 == iso3)
        .distinct()
    ).all()
    schemes = [
        SchemeOut(market=m, group_code=g, name=n, scheme=s, valid_from=f, valid_to=t, source_id=src)
        for m, g, n, s, f, t, src in sorted(rows)
    ]
    surcharges = session.scalars(
        select(TariffMeasure)
        .where(
            TariffMeasure.is_current,
            TariffMeasure.origin_kind == "country",
            TariffMeasure.origin_code == iso3,
            TariffMeasure.code == "*",
        )
        .order_by(TariffMeasure.market_iso3, TariffMeasure.measure_ref)
    )
    out: list[dict[str, Any]] = []
    for m in surcharges:
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
            }
        )
    return OriginDetailOut(origin=_origin(iso3), schemes=schemes, surcharges=out)


# --- tariff news (C2 trade-policy events with their tariff signal, Q-25) -----------------------

NEWS_DAYS = 60
CONFIRM_BEFORE = dt.timedelta(days=30)  # a schedule may change a little before the story
CONFIRM_AFTER = dt.timedelta(days=90)  # or a while after it is announced
_LABEL = {True: "in the schedule", False: "announced, not in the schedule yet"}


def _news_scope() -> list[Any]:
    """Real trade-policy events only (tariffs are real data; scenarios have no tariff news)."""
    return [
        DisruptionEvent.type == "TRADE_POLICY_SANCTION",
        DisruptionEvent.scenario_id.is_(None),
        ~DisruptionEvent.is_synthetic,
    ]


def _agrees(direction: str, change: TariffChange) -> bool:
    delta = change.delta_pp
    if direction == "raise":
        return delta is not None and delta > 0
    if direction == "cut":
        return delta is not None and delta < 0
    if direction == "exempt":
        return change.kind == "exemption" or (delta is not None and delta < 0)
    return False


def _confirmation(
    changes: list[TariffChange], signal: dict[str, Any], published: dt.datetime
) -> TariffChange | None:
    """The schedule change that confirms a story: same market, an origin it names (or a change
    for every origin), the same direction, detected within the window around the story."""
    markets = set(signal.get("markets") or [])
    origins = set(signal.get("origins") or [])
    for c in changes:  # newest first
        if c.market_iso3 not in markets:
            continue
        if origins and c.origin_code not in origins and c.origin_code != "*":
            continue
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
    now = now or dt.datetime.now(dt.UTC)
    q = select(DisruptionEvent).where(*_news_scope())
    if event_id is not None:  # one event, whatever its age (the Radar's drawer asks for it)
        q = q.where(DisruptionEvent.id == event_id)
    else:
        q = q.where(DisruptionEvent.last_updated >= now - dt.timedelta(NEWS_DAYS))
    events = list(session.scalars(q.order_by(DisruptionEvent.first_seen.desc())))
    if not events:
        return []
    rows = session.execute(
        select(EventMention.event_id, EventMention.extracted, Article.url, Article.source_name,
               Article.published_at)
        .join(Article, Article.id == EventMention.article_id)
        .where(EventMention.event_id.in_([e.id for e in events]))
        .order_by(Article.published_at.desc())
    ).all()  # fmt: skip
    by_event: dict[Any, list[Any]] = {}
    for r in rows:
        by_event.setdefault(r.event_id, []).append(r)
    changes = list(session.scalars(select(TariffChange).order_by(TariffChange.detected_at.desc())))
    out: list[NewsOut] = []
    for e in events:
        mentions = by_event.get(e.id, [])
        signals = [m.extracted.get("tariff") for m in mentions if m.extracted.get("tariff")]
        known = [s for s in signals if s.get("direction") != "unknown"]
        signal: dict[str, Any] = (known or signals or [{}])[0]  # newest report first
        if market and market not in (signal.get("markets") or []):
            continue
        if origin and origin not in (signal.get("origins") or []):
            continue
        published = e.first_seen or e.last_updated or now
        hit = _confirmation(changes, signal, published) if signal else None
        quote = (signal.get("spans") or {}).get("direction", {}).get("text")
        out.append(
            NewsOut(
                event_id=str(e.id),
                title=e.title,
                url=mentions[-1].url if mentions else e.url,
                published=published,
                last_updated=e.last_updated or published,
                reports=len(mentions),
                outlets=sorted({m.source_name for m in mentions if m.source_name}),
                source_id=e.source_id,
                direction=str(signal.get("direction") or "unknown"),
                status=str(signal.get("status") or "announced"),
                markets=list(signal.get("markets") or []),
                origins=list(signal.get("origins") or []),
                rate_pct=signal.get("rate_pct"),
                previous_pct=signal.get("previous_pct"),
                industries=list(signal.get("industries") or []),
                effective=signal.get("effective"),
                quote=quote,
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
                data_mode=e.data_mode,
            )
        )
        if len(out) >= limit:
            break
    return out
