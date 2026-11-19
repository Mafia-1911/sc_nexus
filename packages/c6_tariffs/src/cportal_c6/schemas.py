"""C6 API shapes (the API wraps them in its `{data, meta}` envelope)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class MarketOut(BaseModel):
    code: str
    name: str
    live_source: str | None = Field(description="DS-ID of the live schedule, if any")
    last_fetched_at: dt.datetime | None
    data_mode: str | None
    current_measures: int


class OriginOut(BaseModel):
    iso3: str
    name: str


class ProductOut(BaseModel):
    hs6: str
    name: str
    industry: str
    key: str | None = Field(default=None, description="Industry-pack SKU (e.g. TSHIRT)")


class FeedOut(BaseModel):
    id: str
    market: str
    what: str
    status: str = Field(description="live | manual | missing")
    cadence: str | None = None
    note: str | None = None
    todo: str | None = None


class OverviewOut(BaseModel):
    as_of: dt.date | None = Field(description="Date of the precomputed matrix")
    markets: list[MarketOut]
    origins: list[OriginOut]
    products: list[ProductOut]
    feeds: list[FeedOut]
    changes_30d: int
    notices_30d: int
    news_30d: int
    latest_change_at: dt.datetime | None


class CellOut(BaseModel):
    market: str
    hs6: str
    origin: str
    effective_pct_min: float | None
    effective_pct_max: float | None
    is_resolved: bool
    is_stale: bool
    is_ceiling: bool = Field(description="No preference data for this market: an upper bound")
    lower_pct: float | None = Field(None, description="Unresolved: the least this origin pays (None = unknown)")
    upper_pct: float | None = Field(None, description="Unresolved: the most this origin pays (None = unknown)")
    base_pct: float | None
    preference_pct: float | None
    additional_pct: float | None
    n_lines: int
    note_ids: list[int] = Field(description="Indexes into MatrixOut.notes")
    sources: list[str]
    data_mode: str


class MatrixOut(BaseModel):
    as_of: dt.date
    precomputed: bool
    notes: list[str] = Field(description="Each distinct note once; cells point here")
    cells: list[CellOut]


class ComponentOut(BaseModel):
    role: str
    measure_ref: str
    kind: str
    origin_code: str
    origin_name: str | None = Field(default=None, description="Scheme, FTA or country name")
    duty_text: str
    pct: float | None
    legal_ref: str | None
    source_id: str
    source_url: str | None
    valid_from: dt.date | None
    valid_to: dt.date | None
    note: str = ""


class LineRateOut(BaseModel):
    code: str
    description: str | None
    origin: str
    effective_pct: float | None
    is_resolved: bool
    is_stale: bool
    base_pct: float | None
    preference_pct: float | None
    additional_pct: float | None
    lower_pct: float | None = None
    upper_pct: float | None = None
    components: list[ComponentOut]
    notes: list[str]


class ChangeOut(BaseModel):
    id: str
    market: str
    code: str
    hs6: str | None
    kind: str
    origin_code: str
    measure_ref: str
    change: str
    old_duty_text: str | None
    new_duty_text: str | None
    old_pct: float | None
    new_pct: float | None
    delta_pp: float | None
    old_status: str | None
    new_status: str | None
    effective_from: dt.date | None
    detected_at: dt.datetime
    source_id: str
    data_mode: str


class NoticeOut(BaseModel):
    document_number: str
    title: str
    kind: str
    doc_type: str | None
    publication_date: dt.date
    effective_on: dt.date | None
    url: str
    agencies: list[str]
    countries: list[str]
    hts_refs: list[str]
    data_mode: str


class MarketDetailOut(BaseModel):
    market: str
    lines: list[LineRateOut]
    changes: list[ChangeOut]


class ProductDetailOut(BaseModel):
    product: ProductOut
    as_of: dt.date
    origins: list[str]
    markets: list[MarketDetailOut]
    sources: list[str] = Field(description="DS-IDs of the measures used")
    data_modes: dict[str, int] = Field(description="Measures used per data mode")


class SchemeOut(BaseModel):
    market: str
    group_code: str
    name: str
    scheme: str | None
    valid_from: dt.date | None
    valid_to: dt.date | None
    source_id: str


class OriginDetailOut(BaseModel):
    origin: OriginOut
    schemes: list[SchemeOut]
    surcharges: list[dict[str, Any]]


class NewsConfirmationOut(BaseModel):
    change_id: str
    market: str
    measure_ref: str
    origin_code: str
    old_duty_text: str | None
    new_duty_text: str | None
    delta_pp: float | None
    detected_at: dt.datetime


class NewsOut(BaseModel):
    id: str = Field(description="The story (tariff_news row)")
    event_id: str | None = Field(description="C2's disruption event for it, if there is one")
    title: str
    url: str | None
    published: dt.datetime = Field(description="First report")
    last_updated: dt.datetime
    reports: int
    outlets: list[str]
    source_id: str
    direction: str = Field(description="raise | cut | exempt | unknown")
    status: str = Field(description="announced | threatened")
    markets: list[str]
    origins: list[str]
    rate_pct: float | None
    previous_pct: float | None
    industries: list[str]
    effective: str | None
    quote: str | None = Field(description="The words the direction was read from")
    confirmed: bool
    label: str = Field(description="'in the schedule' or 'announced, not in the schedule yet'")
    confirmation: NewsConfirmationOut | None
    data_mode: str
