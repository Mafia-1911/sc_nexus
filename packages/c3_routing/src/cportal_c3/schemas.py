"""C3 request and result shapes (C3 §8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field


class RouteIn(BaseModel):
    origin: str = Field(description="Place key from config/priors/c3.yaml, e.g. BDCGP")
    dest: str = Field(description="Place key, e.g. gazipur")
    depart: AwareDatetime | None = Field(default=None, description="Default: now")
    deadline: AwareDatetime | None = None
    qty_teu: int = Field(default=1, ge=1, le=200)
    cargo_profile: str = Field(default="DRY_CONTAINER", pattern="^(DRY_CONTAINER|REEFER_2_8C)$")
    max_transit_h: float | None = Field(default=None, gt=0, le=240)


class LegOut(BaseModel):
    mode: str
    origin: str
    dest: str
    km: float
    cost_bdt: float
    co2e_kg: float
    factor: dict[str, Any] | None
    note: str
    coords: list[list[float]]


class PlanOut(BaseModel):
    name: str
    modes: list[str]
    km: float
    time_p50_h: float
    time_p90_h: float
    arrival_p50: datetime
    arrival_p90: datetime
    on_time_prob: float | None
    cost_bdt: float
    cost_usd: float
    co2e_kg: float
    co2e_kg_per_teu: float
    pareto_rank: int
    explanation: str
    legs: list[LegOut]
    departures: list[dict[str, Any]]


class RouteResult(BaseModel):
    request_id: str | None = None
    origin: str
    dest: str
    depart: datetime
    deadline: datetime | None
    qty_teu: int
    cargo_profile: str
    plans: list[PlanOut]
    model_version: str
    notes: list[str]
