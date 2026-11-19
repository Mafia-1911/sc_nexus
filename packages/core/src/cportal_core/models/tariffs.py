"""C6 tariff tables (ADR-021): nomenclature, measures, origin groups, snapshots, changes, notices.

How the tables connect (all keyed by `market_iso3`, the importing market; the EU is `EUN`, the
code WITS uses):

- `tariff_nomenclature` is the product tree of one market (heading → HS6 → national lines),
  linked by `parent_code`; `hs6` joins any market's line to the industry packs and to
  `trade_flow`.
- `tariff_measure` is one duty rule: a product scope (`code`, or `*` for "all goods of this
  origin", as US Chapter 99 country surcharges), an origin (every origin, a country or an
  origin group), a kind (MFN, preferential, additional, …) and the verbatim duty text with its
  parsed parts. A measure row is *versioned*: its id includes a hash of its content, so a
  changed rate is a new row and the old one stays as history. `is_current` says whether the
  latest snapshot of its `snapshot_scope` still contains it (maintained by C6).
- `tariff_origin_group` / `tariff_origin_member`: which countries a scheme or FTA covers
  (e.g. UK DCTS Comprehensive ∋ BD).
- `tariff_snapshot`: one per fetched schedule part, listing the measure ids it contained; two
  consecutive snapshots of a scope give `tariff_change` rows.
- `trade_policy_notice`: official notices (Federal Register) that announce or explain changes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import (
    TariffChangeKind,
    TariffMeasureKind,
    TariffOriginKind,
    TariffStatus,
    TradeNoticeKind,
)
from cportal_core.models.base import Base, Lineage, enum_col, fk_uuid, pk


class TariffNomenclature(Lineage, Base):
    __tablename__ = "tariff_nomenclature"
    __extra_args__ = (Index("ix_tariff_nomenclature_market_code", "market_iso3", "code"),)

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    code: Mapped[str] = mapped_column(String(12))  # digits only, e.g. "6109100010"
    code_display: Mapped[str] = mapped_column(String(16))  # as the source writes it
    suffix: Mapped[str | None] = mapped_column(String(4))  # UK product-line suffix ("80")
    level: Mapped[int]  # number of significant digits: 4 heading, 6 HS6, 8/10 national
    hs6: Mapped[str | None] = mapped_column(String(6), index=True)
    parent_code: Mapped[str | None] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text)
    is_declarable: Mapped[bool] = mapped_column(default=False)
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]


class TariffOriginGroup(Lineage, Base):
    __tablename__ = "tariff_origin_group"
    __extra_args__ = (UniqueConstraint("market_iso3", "group_code", "source_id"),)

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    group_code: Mapped[str] = mapped_column(String(32))  # e.g. "1062", "US-SP-AU", "EU-EBA"
    name: Mapped[str] = mapped_column(String(300))
    scheme: Mapped[str | None] = mapped_column(String(64))  # e.g. "DCTS-Comprehensive", "FTA"
    notes: Mapped[str | None] = mapped_column(Text)


class TariffOriginMember(Lineage, Base):
    __tablename__ = "tariff_origin_member"
    __extra_args__ = (Index("ix_tariff_origin_member_country", "member_iso3"),)

    id: Mapped[UUID] = pk()
    group_id: Mapped[UUID] = fk_uuid("tariff_origin_group.id", ondelete="CASCADE")
    market_iso3: Mapped[str] = mapped_column(String(3))
    group_code: Mapped[str] = mapped_column(String(32))
    member_iso2: Mapped[str | None] = mapped_column(String(4))
    member_iso3: Mapped[str | None] = mapped_column(String(3))
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]


class TariffMeasure(Lineage, Base):
    __tablename__ = "tariff_measure"
    __extra_args__ = (
        Index("ix_tariff_measure_lookup", "market_iso3", "hs6", "is_current"),
        Index("ix_tariff_measure_scope", "source_id", "snapshot_scope"),
        Index("ix_tariff_measure_origin", "market_iso3", "origin_code"),
    )

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    code: Mapped[str] = mapped_column(String(12))  # product scope; "*" = all goods of the origin
    hs6: Mapped[str | None] = mapped_column(String(6))
    kind: Mapped[str] = enum_col(TariffMeasureKind)
    origin_kind: Mapped[str] = enum_col(TariffOriginKind)
    origin_code: Mapped[str] = mapped_column(String(32))  # "*", ISO3, or a group_code
    origin_group_id: Mapped[UUID | None] = fk_uuid("tariff_origin_group.id", nullable=True)
    duty_text: Mapped[str] = mapped_column(Text)  # verbatim
    ad_valorem_pct: Mapped[float | None]
    specific_amount: Mapped[float | None]
    specific_unit: Mapped[str | None] = mapped_column(String(32))
    is_compound: Mapped[bool] = mapped_column(default=False)
    is_resolved: Mapped[bool] = mapped_column(default=True)  # False: read the legal text
    measure_ref: Mapped[str] = mapped_column(String(64))  # HTS no., UK measure id, WITS series
    legal_ref: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = enum_col(TariffStatus)
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]
    conditions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    content_hash: Mapped[str] = mapped_column(String(16))
    snapshot_scope: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(default=True)


class TariffSnapshot(Lineage, Base):
    __tablename__ = "tariff_snapshot"
    __extra_args__ = (Index("ix_tariff_snapshot_scope", "source_id", "scope", "fetched_at"),)

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    scope: Mapped[str] = mapped_column(String(64))  # e.g. "hts:6109-6110", "uk:6109100010"
    fetched_at: Mapped[dt.datetime]
    measure_ids: Mapped[list[Any]] = mapped_column(default=list)
    n_measures: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(16))


class TariffChange(Lineage, Base):
    __tablename__ = "tariff_change"
    __extra_args__ = (Index("ix_tariff_change_market_detected", "market_iso3", "detected_at"),)

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    code: Mapped[str] = mapped_column(String(12))
    hs6: Mapped[str | None] = mapped_column(String(6))
    kind: Mapped[str] = enum_col(TariffMeasureKind)
    origin_code: Mapped[str] = mapped_column(String(32))
    measure_ref: Mapped[str] = mapped_column(String(64))
    change: Mapped[str] = enum_col(TariffChangeKind)
    old_measure_id: Mapped[UUID | None]
    new_measure_id: Mapped[UUID | None]
    old_duty_text: Mapped[str | None] = mapped_column(Text)
    new_duty_text: Mapped[str | None] = mapped_column(Text)
    old_ad_valorem_pct: Mapped[float | None]
    new_ad_valorem_pct: Mapped[float | None]
    delta_pp: Mapped[float | None]
    old_status: Mapped[str | None] = mapped_column(String(16))
    new_status: Mapped[str | None] = mapped_column(String(16))
    effective_from: Mapped[dt.date | None]
    detected_at: Mapped[dt.datetime]
    prev_snapshot_id: Mapped[UUID]
    new_snapshot_id: Mapped[UUID]
    scope: Mapped[str] = mapped_column(String(64))


class TradePolicyNotice(Lineage, Base):
    __tablename__ = "trade_policy_notice"
    __extra_args__ = (
        UniqueConstraint("source_id", "document_number"),
        Index("ix_trade_policy_notice_published", "market_iso3", "publication_date"),
    )

    id: Mapped[UUID] = pk()
    market_iso3: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = enum_col(TradeNoticeKind)
    publication_date: Mapped[dt.date]
    effective_on: Mapped[dt.date | None]
    url: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    agencies: Mapped[list[Any]] = mapped_column(default=list)
    countries: Mapped[list[Any]] = mapped_column(default=list)  # ISO3 found in title/abstract
    hts_refs: Mapped[list[Any]] = mapped_column(default=list)  # HTS numbers found in the text


class TariffEffectiveRate(Lineage, Base):
    """Precomputed by C6 (AGENTS rule 7): the duty one origin pays on one HS6 product entering
    one market on `as_of`, across that market's national lines (min / max), with the breakdown
    of a representative line. `source_id` is "C6"; `data_mode` is live if any input was live."""

    __tablename__ = "tariff_effective_rate"
    __extra_args__ = (
        UniqueConstraint("as_of", "market_iso3", "hs6", "origin_iso3"),
        Index("ix_tariff_effective_rate_lookup", "as_of", "market_iso3", "hs6"),
    )

    id: Mapped[UUID] = pk()
    as_of: Mapped[dt.date]
    market_iso3: Mapped[str] = mapped_column(String(3))
    hs6: Mapped[str] = mapped_column(String(6))
    origin_iso3: Mapped[str] = mapped_column(String(3))
    effective_pct_min: Mapped[float | None]
    effective_pct_max: Mapped[float | None]
    is_resolved: Mapped[bool]  # every line resolved to one ad valorem number
    n_lines: Mapped[int]
    base_pct: Mapped[float | None]
    preference_pct: Mapped[float | None]
    additional_pct: Mapped[float | None]
    is_stale: Mapped[bool] = mapped_column(default=False)  # base rate from an earlier year
    # no preference data for this market: the number is the most this origin pays (a ceiling)
    is_ceiling: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # what is known when unresolved: lowest floor, highest ceiling over the lines (None = unknown)
    lower_pct: Mapped[float | None]
    upper_pct: Mapped[float | None]
    components: Mapped[list[Any]] = mapped_column(default=list)  # representative line
    lines: Mapped[list[Any]] = mapped_column(default=list)  # per national line: code, pct
    notes: Mapped[list[Any]] = mapped_column(default=list)
    sources: Mapped[list[Any]] = mapped_column(default=list)  # DS-IDs used
    computed_at: Mapped[dt.datetime]


class TariffNews(Lineage, Base):
    """Tariff news for the Tariff Monitor, written by C2 (Q-25): one row per story (reports of
    the same move grouped), with the tariff signal read from the text. Wider than C2's
    disruption events: a US tariff on Indian textiles is news for Bangladeshi exporters."""

    __tablename__ = "tariff_news"
    __extra_args__ = (Index("ix_tariff_news_published", "first_published"),)

    id: Mapped[UUID] = pk()
    story_key: Mapped[str] = mapped_column(String(200))
    article_ids: Mapped[list[Any]] = mapped_column(default=list)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    outlets: Mapped[list[Any]] = mapped_column(default=list)
    reports: Mapped[int]
    first_published: Mapped[dt.datetime]
    last_published: Mapped[dt.datetime]
    direction: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    markets: Mapped[list[Any]] = mapped_column(default=list)
    origins: Mapped[list[Any]] = mapped_column(default=list)
    rate_pct: Mapped[float | None]
    previous_pct: Mapped[float | None]
    industries: Mapped[list[Any]] = mapped_column(default=list)
    effective: Mapped[str | None] = mapped_column(String(64))
    quote: Mapped[str | None] = mapped_column(Text)
    spans: Mapped[dict[str, Any]] = mapped_column(default=dict)
    event_id: Mapped[UUID | None] = mapped_column(index=True)  # a C2 disruption event, if any
