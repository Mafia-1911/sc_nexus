"""Canonical records: the one schema that live, replay and synthetic data all produce (D-08).

Connectors `parse()` raw responses into these; `packages/sim` generates them; the loader
upserts them into the matching table. A contract test keeps every record in step with its ORM
table (same columns, compatible types), so the API, the DB and the generators cannot drift.

Geometry travels as GeoJSON (RFC 7946, lon/lat) and becomes PostGIS geometry at load time.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from cportal_core.enums import (
    AlertLevel,
    BatchStatus,
    CargoProfile,
    DataMode,
    DiscoveredVia,
    DisruptionType,
    EventClassifier,
    EventStatus,
    FacilityType,
    HolidayKind,
    ImageSplit,
    Industry,
    LocationKind,
    OrderStatus,
    OrgKind,
    PortCallMethod,
    PortCallStatus,
    PortType,
    SatelliteSensor,
    ShipmentStatus,
    ShipTypeGroup,
    TradeFlowDirection,
    TransportEventType,
    TransportMode,
    VisitKind,
    WeatherKind,
    ZoneType,
)

GeoJSON = dict[str, Any]
_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}


def point(lon: float, lat: float) -> GeoJSON:
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


def _check_geojson(value: GeoJSON | None) -> GeoJSON | None:
    if value is None:
        return None
    if value.get("type") not in _GEOMETRY_TYPES or "coordinates" not in value:
        raise ValueError(f"not a GeoJSON geometry: {str(value)[:80]}")
    if value["type"] == "Point":
        lon, lat = value["coordinates"][:2]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"point out of range (lon, lat): {lon}, {lat}")
    return value


class Record(BaseModel):
    """Base of every canonical record: the lineage columns and their rules (04 §4)."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True, validate_assignment=True)

    table: ClassVar[str]
    geometry_fields: ClassVar[tuple[str, ...]] = ()

    id: UUID
    source_id: str = Field(max_length=32)
    source_record_id: str | None = Field(default=None, max_length=256)
    data_mode: DataMode
    is_synthetic: bool = False
    scenario_id: UUID | None = None
    generator_version: str | None = None
    available_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _lineage(self) -> Self:
        if self.is_synthetic != (self.data_mode == DataMode.SYNTHETIC):
            raise ValueError("is_synthetic must be true exactly when data_mode is 'synthetic'")
        if self.is_synthetic and self.scenario_id is None:
            raise ValueError("synthetic records need a scenario_id")
        for name in self.geometry_fields:
            _check_geojson(getattr(self, name))
        return self

    def row(self) -> dict[str, Any]:
        """Column values for the loader (enums as strings, geometry still GeoJSON)."""
        return self.model_dump(mode="python")


# --- Reference and network -------------------------------------------------------------------


class LocationRecord(Record):
    table = "location"
    geometry_fields = ("geom", "geom_area")

    locode: str | None = Field(default=None, pattern=r"^[A-Z]{2}[A-Z2-9]{3}$")
    geonames_id: int | None = None
    name: str
    name_bn: str | None = None
    country_iso2: str | None = Field(default=None, min_length=2, max_length=2)
    kind: LocationKind
    cluster: str | None = None
    geom: GeoJSON | None = None
    geom_area: GeoJSON | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class PortRecord(Record):
    table = "port"

    location_id: UUID
    locode: str | None = None
    name: str
    port_type: PortType
    operator: str | None = None
    max_draught_m: float | None = Field(default=None, gt=0)
    max_loa_m: float | None = Field(default=None, gt=0)
    tidal: bool = False
    berths_count_by_class: dict[str, Any] = Field(default_factory=dict)


class PortZoneRecord(Record):
    table = "port_zone"
    geometry_fields = ("geom",)

    port_id: UUID
    zone_type: ZoneType
    name: str
    cell_id: str | None = None
    geom: GeoJSON | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class ExternalIdRecord(Record):
    table = "external_id"

    entity_type: str
    entity_id: UUID
    scheme: str
    value: str
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class OrganizationRecord(Record):
    table = "organization"

    name: str
    name_key: str | None = None
    country_iso2: str | None = None
    kind: OrgKind
    industry: Industry | None = None
    lei: str | None = None
    osh_id: str | None = None
    wikidata_qid: str | None = None
    is_fictional: bool
    attrs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _guardrail(self) -> Self:
        # Rule 3: synthetic firms are fictional. Real firms never come from a generator.
        if self.is_synthetic and not self.is_fictional:
            raise ValueError("a synthetic organization must be fictional (AGENTS.md rule 3)")
        return self


class FacilityRecord(Record):
    table = "facility"

    organization_id: UUID
    name: str
    name_key: str | None = None
    facility_type: FacilityType
    location_id: UUID
    cluster: str | None = None
    capacity: dict[str, Any] = Field(default_factory=dict)
    certifications: list[Any] = Field(default_factory=list)


class ProductRecord(Record):
    table = "product"

    sku: str
    name: str
    industry: Industry
    hs6: str | None = Field(default=None, pattern=r"^\d{6}$")
    gtin: str | None = None
    uom: str
    unit_value_usd: float | None = Field(default=None, ge=0)
    cold_chain: bool = False
    temp_range_c: list[float] | None = None
    shelf_life_days: int | None = Field(default=None, gt=0)
    hazardous: bool = False


class BomEdgeRecord(Record):
    table = "bom_edge"

    parent_product_id: UUID
    component_product_id: UUID
    qty_per_unit: float = Field(gt=0)


class LaneRecord(Record):
    table = "lane"
    geometry_fields = ("geom",)

    origin_location_id: UUID
    dest_location_id: UUID
    mode: TransportMode
    via: list[str] = Field(default_factory=list)
    distance_km: float | None = Field(default=None, ge=0)
    typical_transit_d: float | None = Field(default=None, ge=0)
    geom: GeoJSON | None = None


class SupplyEdgeRecord(Record):
    table = "supply_edge"

    from_facility_id: UUID
    to_facility_id: UUID
    product_id: UUID
    share: float = Field(ge=0, le=1)
    capacity_per_week: float | None = Field(default=None, ge=0)
    lead_time_mean_d: float = Field(ge=0)
    lead_time_sd_d: float | None = Field(default=None, ge=0)
    mode: TransportMode
    lane_id: UUID | None = None
    cost_per_unit_usd: float | None = Field(default=None, ge=0)
    is_inferred: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class HolidayRecord(Record):
    table = "holiday"

    date: dt.date
    kind: HolidayKind
    name: str
    country_iso2: str = Field(min_length=2, max_length=2)
    notice_url: str | None = None


class EmissionFactorRecord(Record):
    table = "emission_factor"

    mode: TransportMode
    vehicle_class: str
    fuel: str | None = None
    unit: str
    ghg_unit: str
    value: float = Field(ge=0)
    scope: str
    year: int


class TradeFlowRecord(Record):
    table = "trade_flow"

    reporter_iso3: str = Field(min_length=3, max_length=3)
    partner_iso3: str = Field(min_length=3, max_length=3)
    hs_code: str
    year: int
    flow: TradeFlowDirection
    value_usd: float | None = Field(default=None, ge=0)
    net_wgt_kg: float | None = Field(default=None, ge=0)
    is_mirror: bool = False


class CountryIndicatorRecord(Record):
    table = "country_indicator"

    country_iso3: str = Field(min_length=3, max_length=3)
    indicator_code: str
    indicator_name: str
    year: int
    value: float | None = None
    unit: str | None = None


# --- Maritime ----------------------------------------------------------------------------------


class VesselRecord(Record):
    table = "vessel"

    imo: str | None = Field(default=None, pattern=r"^\d{7}$")
    mmsi: int | None = Field(default=None, ge=100_000_000, le=999_999_999)
    name: str | None = None
    call_sign: str | None = None
    ship_type_ais: int | None = Field(default=None, ge=0, le=99)
    ship_type_group: ShipTypeGroup | None = None
    loa_m: float | None = Field(default=None, gt=0, lt=500)
    beam_m: float | None = Field(default=None, gt=0, lt=80)
    dwt: float | None = Field(default=None, ge=0)
    gt: float | None = Field(default=None, ge=0)
    flag_iso3: str | None = Field(default=None, min_length=3, max_length=3)


class AisPositionRecord(Record):
    """One AIS position. History goes to Parquet; the newest per vessel to Postgres (ADR-003).
    SC-08: `ts` is the receiver time, `received_at` our time; sentinels are already null."""

    table = "ais_position_latest"
    geometry_fields = ("geom",)

    vessel_id: UUID | None = None
    mmsi: int = Field(ge=100_000_000, le=999_999_999)
    ts: AwareDatetime
    received_at: AwareDatetime | None = None
    msg_type: str | None = None
    geom: GeoJSON
    sog_kn: float | None = Field(default=None, ge=0, lt=102.3)
    cog_deg: float | None = Field(default=None, ge=0, lt=360)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    nav_status: int | None = Field(default=None, ge=0, le=15)
    draught_m: float | None = Field(default=None, ge=0, lt=30)
    destination: str | None = None
    eta_reported: AwareDatetime | None = None


class PortCallRecord(Record):
    table = "port_call"

    vessel_id: UUID
    port_id: UUID
    status: PortCallStatus
    visit_kind: VisitKind | None = None
    arrival_ts: AwareDatetime | None = None
    anchorage_start_ts: AwareDatetime | None = None
    anchorage_end_ts: AwareDatetime | None = None
    berth_start_ts: AwareDatetime | None = None
    berth_end_ts: AwareDatetime | None = None
    departure_ts: AwareDatetime | None = None
    departure_planned_ts: AwareDatetime | None = None
    waiting_h: float | None = Field(default=None, ge=0)
    berth_h: float | None = Field(default=None, ge=0)
    dwell_h: float | None = Field(default=None, ge=0)
    berth_zone_id: UUID | None = None
    censored: bool = False
    method: PortCallMethod
    confidence: int | None = Field(default=None, ge=1, le=4)
    gfw_visit_id: str | None = None
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _order(self) -> Self:
        a, b = self.anchorage_start_ts, self.berth_start_ts
        if a and b and b < a:
            raise ValueError("berth_start_ts precedes anchorage_start_ts")
        if self.arrival_ts and self.departure_ts and self.departure_ts < self.arrival_ts:
            raise ValueError("departure_ts precedes arrival_ts")
        return self


class PortCallStopRecord(Record):
    table = "port_call_stop"
    geometry_fields = ("geom",)

    port_call_id: UUID
    seq: int = Field(ge=0)
    cell_id: str | None = None
    zone_id: UUID | None = None
    at_dock: bool = False
    geom: GeoJSON | None = None
    start_ts: AwareDatetime | None = None
    end_ts: AwareDatetime | None = None


class PortActivityDailyRecord(Record):
    table = "port_activity_daily"

    port_id: UUID
    date: dt.date
    calls_total: int | None = Field(default=None, ge=0)
    calls_by_type: dict[str, int] = Field(default_factory=dict)
    import_t: float | None = Field(default=None, ge=0)
    export_t: float | None = Field(default=None, ge=0)
    trade_by_type: dict[str, float] = Field(default_factory=dict)


class ZonePresenceDailyRecord(Record):
    table = "zone_presence_daily"

    zone_id: UUID | None = None
    area_name: str
    date: dt.date
    vessel_id: UUID | None = None
    mmsi: int | None = None
    imo: str | None = None
    ship_type_group: ShipTypeGroup | None = None
    hours: float = Field(ge=0, le=24.0001)
    mean_sog_kn: float | None = Field(default=None, ge=0)
    entry_ts: AwareDatetime | None = None
    exit_ts: AwareDatetime | None = None


class SatelliteObservationRecord(Record):
    table = "satellite_observation"
    geometry_fields = ("footprint",)

    sensor: SatelliteSensor
    scene_id: str | None = None
    acq_ts: AwareDatetime
    area_name: str | None = None
    zone_id: UUID | None = None
    footprint: GeoJSON | None = None
    asset_href: str | None = None
    cloud_pct: float | None = Field(default=None, ge=0, le=100)
    detections_count: int | None = Field(default=None, ge=0)
    detections: list[Any] = Field(default_factory=list)


class WeatherObservationRecord(Record):
    table = "weather_observation"
    geometry_fields = ("geom",)

    point_name: str
    location_id: UUID | None = None
    geom: GeoJSON | None = None
    ts: AwareDatetime
    kind: WeatherKind
    issued_at: AwareDatetime | None = None
    temperature_2m_c: float | None = None
    precipitation_mm: float | None = Field(default=None, ge=0)
    wind_speed_10m_kmh: float | None = Field(default=None, ge=0)
    wind_gusts_10m_kmh: float | None = Field(default=None, ge=0)
    wind_direction_10m_deg: float | None = Field(default=None, ge=0, le=360)
    pressure_msl_hpa: float | None = None
    wave_height_m: float | None = Field(default=None, ge=0)
    wave_period_s: float | None = Field(default=None, ge=0)
    swell_wave_height_m: float | None = Field(default=None, ge=0)
    sea_level_height_msl_m: float | None = None
    ocean_current_velocity_kmh: float | None = Field(default=None, ge=0)


# --- Events ------------------------------------------------------------------------------------


class ArticleRecord(Record):
    table = "article"

    url: str
    url_canonical: str
    source_name: str | None = None
    published_at: AwareDatetime | None = None
    lang: str | None = None
    source_lang: str | None = None
    title: str | None = None
    snippet: str | None = Field(default=None, max_length=300)
    content_hash: str | None = None
    discovered_via: DiscoveredVia
    feed_id: str | None = None
    gdelt_ids: list[Any] = Field(default_factory=list)
    themes: list[Any] = Field(default_factory=list)
    locations: list[Any] = Field(default_factory=list)
    tone: float | None = None

    @field_validator("snippet", mode="before")
    @classmethod
    def _clip(cls, value: str | None) -> str | None:
        # News copyright guardrail (03 §5): never more than 300 characters.
        return None if value is None else value[:300]


class DisruptionEventRecord(Record):
    table = "disruption_event"
    geometry_fields = ("geom",)

    type: DisruptionType
    subtype: str | None = None
    title: str
    summary: str | None = None
    status: EventStatus
    severity: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    alert_level: AlertLevel | None = None
    start_est: AwareDatetime | None = None
    start_uncertainty_h: float | None = Field(default=None, ge=0)
    end_est: AwareDatetime | None = None
    duration_p50_h: float | None = Field(default=None, ge=0)
    duration_p90_h: float | None = Field(default=None, ge=0)
    geom: GeoJSON | None = None
    locodes: list[str] = Field(default_factory=list)
    country_iso3: list[str] = Field(default_factory=list)
    first_seen: AwareDatetime | None = None
    last_updated: AwareDatetime | None = None
    cluster_key: str | None = None
    external_ids: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None


# --- Vision ------------------------------------------------------------------------------------


class ImageDatasetRecord(Record):
    table = "image_dataset"

    dataset_ref: str
    title: str
    licence: str | None = None
    nc: bool = False
    url: str | None = None
    task: str
    categories: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    n_images: int | None = Field(default=None, ge=0)
    splits: dict[str, int] = Field(default_factory=dict)
    size_bytes: int | None = Field(default=None, ge=0)


class InspectionImageRecord(Record):
    table = "inspection_image"

    dataset_id: UUID | None = None
    batch_id: UUID | None = None
    product_id: UUID | None = None
    category: str
    split: ImageSplit | None = None
    label: str | None = None
    uri: str
    mask_uri: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    captured_at: AwareDatetime | None = None
    source_dataset: str


class BatchRecord(Record):
    table = "batch"

    lot_code: str
    product_id: UUID
    facility_id: UUID
    supplier_facility_id: UUID | None = None
    line: str | None = None
    shift: str | None = None
    size_units: int = Field(gt=0)
    produced_at: AwareDatetime
    status: BatchStatus
    aql_level: str | None = None
    aql_result: dict[str, Any] = Field(default_factory=dict)


# --- Orders, inventory, shipments ----------------------------------------------------------------


class CustomerOrderRecord(Record):
    table = "customer_order"

    reference: str
    buyer_org_id: UUID
    product_id: UUID
    facility_id: UUID | None = None
    qty: float = Field(gt=0)
    due_date: dt.date
    incoterm: str | None = Field(default=None, max_length=3)
    priority: int = Field(default=3, ge=1, le=5)
    status: OrderStatus
    revenue_usd: float | None = Field(default=None, ge=0)


class InventoryPositionRecord(Record):
    table = "inventory_position"

    facility_id: UUID
    product_id: UUID
    ts: AwareDatetime
    on_hand: float = Field(ge=0)
    on_order: float = Field(default=0.0, ge=0)
    allocated: float = Field(default=0.0, ge=0)
    safety_stock: float | None = Field(default=None, ge=0)
    reorder_point: float | None = Field(default=None, ge=0)
    days_of_cover: float | None = Field(default=None, ge=0)


class ShipmentRecord(Record):
    table = "shipment"

    reference: str
    mode_chain: list[TransportMode] = Field(default_factory=list)
    origin_location_id: UUID
    dest_location_id: UUID
    containers: list[str] = Field(default_factory=list)
    cargo_profile: CargoProfile
    planned_eta: AwareDatetime | None = None
    predicted_eta_p50: AwareDatetime | None = None
    predicted_eta_p90: AwareDatetime | None = None
    status: ShipmentStatus


class ShipmentOrderRecord(Record):
    table = "shipment_order"

    shipment_id: UUID
    order_id: UUID
    qty: float | None = Field(default=None, gt=0)


class ShipmentLegRecord(Record):
    table = "shipment_leg"

    shipment_id: UUID
    seq: int = Field(ge=0)
    mode: TransportMode
    from_location_id: UUID
    to_location_id: UUID
    vessel_id: UUID | None = None
    planned_dep: AwareDatetime | None = None
    planned_arr: AwareDatetime | None = None
    actual_dep: AwareDatetime | None = None
    actual_arr: AwareDatetime | None = None
    route_option_id: UUID | None = None


class TransportEventRecord(Record):
    table = "transport_event"

    shipment_id: UUID
    event_type: TransportEventType
    classifier: EventClassifier
    event_code: str = Field(max_length=8)
    location_id: UUID | None = None
    event_ts: AwareDatetime
    vessel_id: UUID | None = None
    equipment_reference: str | None = Field(default=None, pattern=r"^[A-Z]{4}\d{7}$")


class ScenarioRecord(Record):
    table = "scenario"

    key: str
    name: str
    definition: dict[str, Any] = Field(default_factory=dict)
    seed: int
    is_baseline: bool = False
    created_by: str | None = None


RECORD_TYPES: tuple[type[Record], ...] = (
    LocationRecord,
    PortRecord,
    PortZoneRecord,
    ExternalIdRecord,
    OrganizationRecord,
    FacilityRecord,
    ProductRecord,
    BomEdgeRecord,
    LaneRecord,
    SupplyEdgeRecord,
    HolidayRecord,
    EmissionFactorRecord,
    TradeFlowRecord,
    CountryIndicatorRecord,
    VesselRecord,
    AisPositionRecord,
    PortCallRecord,
    PortCallStopRecord,
    PortActivityDailyRecord,
    ZonePresenceDailyRecord,
    SatelliteObservationRecord,
    WeatherObservationRecord,
    ArticleRecord,
    DisruptionEventRecord,
    ImageDatasetRecord,
    InspectionImageRecord,
    BatchRecord,
    CustomerOrderRecord,
    InventoryPositionRecord,
    ShipmentRecord,
    ShipmentOrderRecord,
    ShipmentLegRecord,
    TransportEventRecord,
    ScenarioRecord,
)
