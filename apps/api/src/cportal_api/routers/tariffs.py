"""/tariffs: the Tariff Monitor (C6, ADR-021). Real data only: tariff schedules have no
scenario rows, so the scenario selector does not change these answers.

Every response carries the DS-IDs and the data mode of the rows behind it (LIVE when fetched
by the worker, REPLAY when loaded from the committed samples), so the UI badges each view.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Annotated, Any, cast
from uuid import UUID

from cportal_c6 import ENGINE_VERSION, service
from cportal_c6.schemas import (
    ChangeOut,
    MatrixOut,
    NewsOut,
    NoticeOut,
    OriginDetailOut,
    OverviewOut,
    ProductDetailOut,
)
from cportal_core.enums import TradeNoticeKind
from fastapi import APIRouter, HTTPException, Query

from cportal_api.deps import SessionDep
from cportal_api.schemas import Envelope, Meta, ModeLabel

router = APIRouter(prefix="/tariffs", tags=["tariffs"])

CodeList = Annotated[list[str] | None, Query(description="Repeat or comma-separate")]
NOTE = "Information, not legal or customs advice: check the official schedule (source links)."


def _split(values: list[str] | None, upper: bool = True) -> list[str] | None:
    if not values:
        return None
    out = [v.strip() for value in values for v in value.split(",") if v.strip()]
    return [v.upper() for v in out] if upper else out


def _meta(modes: Counter[str], sources: set[str], note: str | None = NOTE) -> Meta:
    label: ModeLabel = "none" if not modes else "mixed"
    if len(modes) == 1:
        label = cast(ModeLabel, next(iter(modes)))
    return Meta(
        mode=label,
        modes=dict(modes),
        sources=sorted(sources),
        as_of=dt.datetime.now(dt.UTC),
        model_version=ENGINE_VERSION,
        note=note,
    )


def _rows_meta(rows: list[Any], source_attr: str = "source_id") -> Meta:
    return _meta(
        Counter(str(r.data_mode) for r in rows), {str(getattr(r, source_attr)) for r in rows}
    )


@router.get("/overview", response_model=Envelope[OverviewOut])
def overview(session: SessionDep) -> Envelope[OverviewOut]:
    """Markets with their feeds and last fetch, origins, watched products, feed status (live,
    manual, missing) and recent change and notice counts: the page header."""
    data = service.overview(session)
    modes = Counter(m.data_mode for m in data.markets if m.data_mode)
    return Envelope(
        data=data, meta=_meta(modes, {m.live_source for m in data.markets if m.live_source})
    )


@router.get("/matrix", response_model=Envelope[MatrixOut])
def matrix(
    session: SessionDep,
    as_of: dt.date | None = None,
    hs6: CodeList = None,
    market: CodeList = None,
    origin: CodeList = None,
    industry: str | None = None,
) -> Envelope[MatrixOut]:
    """Effective duty per market × HS6 product × origin (min and max over national lines). A
    date that was not precomputed is computed on the fly (`precomputed: false`)."""
    data = service.matrix(
        session, as_of, _split(hs6, upper=False), _split(market), _split(origin), industry
    )
    modes = Counter(c.data_mode for c in data.cells)
    return Envelope(data=data, meta=_meta(modes, {s for c in data.cells for s in c.sources}))


@router.get("/products/{hs6}", response_model=Envelope[ProductDetailOut])
def product(
    session: SessionDep,
    hs6: str,
    as_of: dt.date | None = None,
    market: CodeList = None,
    origin: CodeList = None,
) -> Envelope[ProductDetailOut]:
    """One product: per market and origin, every national line with its rate breakdown (base,
    preference, surcharges, possible exemptions) and legal references; recent changes."""
    if not (len(hs6) == 6 and hs6.isdigit()):
        raise HTTPException(422, "hs6 must be six digits")
    data = service.product(session, hs6, as_of, _split(market), _split(origin))
    if data is None:
        raise HTTPException(404, f"HS {hs6} is not a watched product")
    return Envelope(data=data, meta=_meta(Counter(data.data_modes), set(data.sources)))


@router.get("/changes", response_model=Envelope[list[ChangeOut]])
def changes(
    session: SessionDep,
    market: str | None = None,
    origin: str | None = None,
    hs6: str | None = None,
    since: dt.datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Envelope[list[ChangeOut]]:
    """Detected changes between snapshots of the official schedules, newest first."""
    data = service.changes(
        session, market and market.upper(), origin and origin.upper(), hs6, since, limit
    )
    return Envelope(data=data, meta=_rows_meta(data))


@router.get("/notices", response_model=Envelope[list[NoticeOut]])
def notices(
    session: SessionDep,
    kind: TradeNoticeKind | None = None,
    country: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[NoticeOut]]:
    """Official trade notices (US Federal Register: USTR, ITA, ITC, CBP), newest first."""
    data = service.notices(
        session, kind.value if kind else None, country and country.upper(), limit
    )
    return Envelope(
        data=data,
        meta=_meta(Counter(n.data_mode for n in data), {"DS-TRADE-06"} if data else set()),
    )


@router.get("/origins/{iso3}", response_model=Envelope[OriginDetailOut])
def origin(
    session: SessionDep, iso3: str, as_of: dt.date | None = None
) -> Envelope[OriginDetailOut]:
    """A country's tariff relations: the schemes and FTAs that cover it in each market, and
    the country-wide surcharges it pays (e.g. US Chapter 99)."""
    if not (len(iso3) == 3 and iso3.isalpha()):
        raise HTTPException(422, "iso3 must be three letters")
    data = service.origin_detail(session, iso3.upper(), as_of)
    sources = {s.source_id for s in data.schemes}
    return Envelope(data=data, meta=_meta(Counter(), sources))


@router.get("/news", response_model=Envelope[list[NewsOut]])
def news(
    session: SessionDep,
    market: str | None = None,
    origin: str | None = None,
    event_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[NewsOut]]:
    """Tariff news from the C2 news pipeline (RSS, GDELT), newest first: direction, market,
    origin and rates read from the text, and whether the official schedule already shows it."""
    data = service.news(
        session, market and market.upper(), origin and origin.upper(), limit, event_id=event_id
    )
    return Envelope(data=data, meta=_rows_meta(data))
