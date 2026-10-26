"""C1 output contract (C1 §4): node metrics and what-if results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Driver(BaseModel):
    """One feature's share of a node's risk score. The score is additive, so these are its
    exact Shapley values against the mean node (SHAP with an interventional baseline)."""

    feature: str
    label: str
    value: float  # the feature, 0–1
    contribution: float  # points of risk score vs the average node


class NodeMetrics(BaseModel):
    node_id: str
    kind: str
    type: str
    name: str
    industry: str | None
    downstream_products: list[str]
    downstream_orders: int
    downstream_open_order_value_usd: float
    dominated_products: list[str]
    dominated_order_ids: list[str] = Field(default_factory=list)
    dominated_orders: int
    dominated_value_usd: float
    betweenness: float
    pagerank_rev: float
    hhi_inputs: dict[str, float]
    single_sourced_inputs: list[str]
    sole_source_for: list[dict[str, str]]
    tts_d: float | None
    tts_capped: bool = False
    ttr_d: float | None
    ttr_p90_d: float | None
    ttr_source: str | None
    performance_impact_usd: float | None
    risk_score: float | None
    risk_band: str | None
    risk_drivers: list[Driver] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    model_version: str


class DisruptionIn(BaseModel):
    node_id: str
    duration_d: float = Field(gt=0, le=180)
    capacity_pct: float = Field(default=0.0, ge=0, le=100)
    start_d: float = Field(default=0.0, ge=0, le=90)
    extra_lead_time_d: float = Field(default=0.0, ge=0, le=60)


class WhatIfRequest(BaseModel):
    disruptions: list[DisruptionIn] = Field(min_length=1, max_length=10)
    mc_runs: int = Field(default=0, ge=0, le=500)
    seed: int = 42


class OrderImpactOut(BaseModel):
    order_id: str
    reference: str
    buyer: str
    product: str
    facility: str
    facility_name: str
    due: str
    revenue_usd: float
    delay_d: float
    late: bool
    cause: str


class Mitigation(BaseModel):
    action_type: str  # dual_source | increase_safety_stock | reroute | expedite
    title: str
    detail: str
    targets: list[str] = Field(default_factory=list)


class WhatIfResult(BaseModel):
    disrupted: list[DisruptionIn]
    duration_d: float
    capacity_pct: float
    mc_runs: int
    seed: int
    first_impact_d: float | None
    recovery_d: float | None
    tts_d: float | None
    orders_late: int
    revenue_at_risk_usd: float
    revenue_at_risk_usd_p50: float | None = None
    revenue_at_risk_usd_p90: float | None = None
    orders_late_p50: float | None = None
    orders_late_p90: float | None = None
    recovery_d_p50: float | None = None
    recovery_d_p90: float | None = None
    timeline: list[dict[str, Any]]
    impacted_orders: list[OrderImpactOut]
    mitigations: list[Mitigation]
    model_version: str
