"""C4 response shapes (C4 §8): queue forecast, vessels in port with predictions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Band(BaseModel):
    p10: float
    p50: float
    p90: float


class QueueForecastOut(BaseModel):
    locode: str
    as_of: datetime
    snapshots: list[datetime] = Field(description="Replay times with predictions (noon, Dhaka)")
    history: list[tuple[str, float]] = Field(description="Vessels in the outer anchorage per day")
    forecast: list[tuple[str, float, float, float]] = Field(description="Date, P10, P50, P90")
    metrics: dict[str, Any] = Field(default_factory=dict)


class VesselInPortOut(BaseModel):
    call_id: UUID
    vessel_id: UUID
    mmsi: int | None
    name: str | None
    ship_type: str | None
    flag: str | None
    arrival_ts: datetime
    elapsed_h: float
    dwell_at_arrival: Band | None = Field(None, description="L1 at arrival, hours")
    baseline_at_arrival: Band | None = Field(None, description="L0 median, hours")
    remaining: Band = Field(description="L2: hours left in port as of the snapshot")
    departure_p10: datetime
    departure_p50: datetime
    departure_p90: datetime
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    actual_departure_ts: datetime | None = Field(None, description="Replay only: what happened")
    actual_dwell_h: float | None = None


class VesselTrackOut(BaseModel):
    """One call's predictions as time passes (C4-R03): the departure estimate per snapshot."""

    vessel: VesselInPortOut
    updates: list[dict[str, Any]]
