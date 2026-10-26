"""API envelope and shared response models (04 §7).

Every data response is `{data, meta}`; `meta` carries the data mode, the DS-IDs behind the data,
`as_of` and the model version, so the UI renders the LIVE / REPLAY / SYNTHETIC badge from it.
Lists are cursor-paginated. Errors are RFC 9457 problem+json. Geometries are GeoJSON.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

ModeLabel = Literal["live", "replay", "synthetic", "mixed", "none"]


class Meta(BaseModel):
    mode: ModeLabel = Field(description="Badge for the UI: one mode, or 'mixed'")
    modes: dict[str, int] = Field(default_factory=dict, description="Rows per data mode")
    sources: list[str] = Field(default_factory=list, description="DS-IDs (or 'sim')")
    as_of: AwareDatetime
    scenario: str | None = None
    model_version: str | None = None
    note: str | None = None


class Envelope[T](BaseModel):
    data: T
    meta: Meta


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    limit: int


class Problem(BaseModel):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class JobAccepted(BaseModel):
    job_id: UUID
    status: str
    poll: str


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]


def encode_cursor(*parts: Any) -> str:
    raw = json.dumps([p.isoformat() if isinstance(p, datetime) else str(p) for p in parts])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> list[str]:
    padded = cursor + "=" * (-len(cursor) % 4)
    value: list[str] = json.loads(base64.urlsafe_b64decode(padded.encode()))
    return value


# --- resources ----------------------------------------------------------------------------------


class SourceOut(BaseModel):
    ds_id: str
    name: str
    tier: str
    status: str
    default_mode: str | None
    fallback: str | None
    nc: bool
    last_success_ts: datetime | None
    freshness_h: float | None = Field(None, description="Hours since the last successful run")
    licence: str | None = None
    cadence: str | None = None
    effective_mode: str | None = Field(None, description="Mode in use after two strikes")
    failures: int = 0
    last_error: str | None = None
    records_last_run: int | None = None


class ScenarioOut(BaseModel):
    key: str
    name: str
    is_baseline: bool
    seed: int
    definition: dict[str, Any]


class ScenarioResultOut(BaseModel):
    capability: str
    kpis: dict[str, Any]
    artifacts: dict[str, Any]


class PortOut(BaseModel):
    id: UUID
    locode: str | None
    name: str
    port_type: str
    tidal: bool
    max_draught_m: float | None
    geometry: dict[str, Any] | None


class PortStateOut(BaseModel):
    ts: datetime
    queue_by_type: dict[str, Any]
    berth_occupancy: dict[str, Any]
    arrivals_24h: int | None
    departures_24h: int | None
    mean_wait_h_24h: float | None
    tide: dict[str, Any]


class PortCallOut(BaseModel):
    id: UUID
    vessel_id: UUID
    vessel_name: str | None
    status: str
    visit_kind: str | None
    method: str
    arrival_ts: datetime | None
    berth_start_ts: datetime | None
    departure_ts: datetime | None
    waiting_h: float | None
    berth_h: float | None
    dwell_h: float | None
    quality_flags: list[Any]
    data_mode: str
    source_id: str


class ActivityOut(BaseModel):
    date: str
    calls_total: int | None
    calls_by_type: dict[str, Any]
    import_t: float | None
    export_t: float | None


class EventOut(BaseModel):
    id: UUID
    type: str
    subtype: str | None
    title: str
    status: str
    severity: float | None
    confidence: float | None
    alert_level: str | None
    start_est: datetime | None
    end_est: datetime | None
    locodes: list[str]
    country_iso3: list[str]
    geometry: dict[str, Any] | None
    source_id: str
    data_mode: str


class GraphOut(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ShipmentOut(BaseModel):
    id: UUID
    reference: str
    status: str
    mode_chain: list[Any]
    cargo_profile: str
    planned_eta: datetime | None
    predicted_eta_p50: datetime | None
    predicted_eta_p90: datetime | None
    legs: list[dict[str, Any]] = Field(default_factory=list)


class BatchOut(BaseModel):
    id: UUID
    lot_code: str
    status: str
    produced_at: datetime
    size_units: int
    aql_result: dict[str, Any]
    facility: str
    supplier: str | None


class DatasetOut(BaseModel):
    dataset_ref: str
    title: str
    licence: str | None
    nc: bool
    task: str
    n_images: int | None
    classes: list[Any]


class ModelOut(BaseModel):
    capability: str
    name: str
    version: str
    is_active: bool
    licence: str | None
    metrics: dict[str, Any]


class BrandOut(BaseModel):
    brand: str
    name_pack: str
    banner: str | None
    has_real_names: bool
    version: str


class Kpi(BaseModel):
    key: str
    label: str
    value: float | int | None
    unit: str | None = None
    detail: str | None = None
    meta: Meta


class KpiStrip(BaseModel):
    kpis: list[Kpi]
