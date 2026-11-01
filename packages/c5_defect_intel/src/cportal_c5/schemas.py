"""C5 response shapes (C5 §8): lots and their AQL, inspected items, lines and SPC, live results."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LotOut(BaseModel):
    id: UUID
    lot_code: str
    sku: str
    product: str
    industry: str
    category: str | None
    facility_id: UUID
    facility: str
    cluster: str | None = Field(None, description="Plant cluster (a Route Planner place)")
    line: str | None
    shift: str | None
    size_units: int
    produced_at: datetime
    status: str
    decision: str | None = Field(None, description="accept | reject | qa_review_required")
    sample_size: int | None = None
    accept: int | None = None
    confirmed_defects: int | None = None
    flagged: int | None = None
    false_alarms: int | None = None
    risk_before: float | None = Field(None, description="P(fail AQL) forecast before inspection")
    order_ref: str | None = None
    order_due: date | None = None
    alert_id: UUID | None = None


class ItemOut(BaseModel):
    id: UUID
    category: str
    label: str | None = Field(None, description="Ground truth of the source image")
    image_url: str
    heatmap_url: str | None
    score: float
    threshold: float
    flagged: bool
    source_dataset: str


class LotOptionOut(BaseModel):
    id: UUID
    action_type: str
    expected_cost_usd: float | None
    expected_benefit_usd: float | None
    confidence: float | None
    rationale: str | None
    params: dict[str, Any]
    status: str


class LotDetailOut(BaseModel):
    lot: LotOut
    aql: dict[str, Any]
    items: list[ItemOut]
    order: dict[str, Any] | None
    alert: dict[str, Any] | None
    recommendations: list[LotOptionOut]
    line: dict[str, Any] | None


class LineOut(BaseModel):
    id: UUID
    facility_id: UUID
    facility: str
    line: str
    industry: str
    p_fail_next: float
    rate: float
    alarm_now: bool
    alarms: int


class SpcOut(BaseModel):
    line: LineOut | None
    center: float
    ewma_ucl: float
    points: list[dict[str, Any]]


class LiveResultOut(BaseModel):
    category: str
    score: float
    threshold: float
    flagged: bool
    image_url: str
    heatmap_url: str
    latency_ms: float
    method: str
