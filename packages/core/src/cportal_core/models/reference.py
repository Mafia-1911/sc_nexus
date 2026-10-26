"""Reference data and the supply network: places, ports, zones, firms, facilities, products."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import (
    FacilityType,
    HolidayKind,
    Industry,
    LocationKind,
    OrgKind,
    PortType,
    TransportMode,
    ZoneType,
)
from cportal_core.models.base import (
    EMBEDDING_DIM,
    Base,
    Lineage,
    enum_col,
    fk_uuid,
    geom_col,
    pk,
)


class Location(Lineage, Base):
    """Any place: country, city, port, ICD, cluster, site. UN/LOCODE is unique where present."""

    __tablename__ = "location"
    __extra_args__ = (
        Index(
            "uq_location_locode_scope",
            "locode",
            text("coalesce(scenario_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("locode IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = pk()
    locode: Mapped[str | None] = mapped_column(String(5))
    geonames_id: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_bn: Mapped[str | None] = mapped_column(String(200))
    country_iso2: Mapped[str | None] = mapped_column(String(2), index=True)
    kind: Mapped[str] = enum_col(LocationKind, index=True)
    cluster: Mapped[str | None] = mapped_column(String(40), index=True)
    geom: Mapped[Any] = geom_col("POINT")
    geom_area: Mapped[Any] = geom_col("MULTIPOLYGON")
    attrs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class Port(Lineage, Base):
    __tablename__ = "port"

    id: Mapped[UUID] = pk()
    location_id: Mapped[UUID] = fk_uuid("location.id")
    locode: Mapped[str | None] = mapped_column(String(5), index=True)
    name: Mapped[str] = mapped_column(String(200))
    port_type: Mapped[str] = enum_col(PortType)
    operator: Mapped[str | None] = mapped_column(String(200))
    max_draught_m: Mapped[float | None]
    max_loa_m: Mapped[float | None]
    tidal: Mapped[bool] = mapped_column(default=False)
    berths_count_by_class: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'")
    )


class PortZone(Lineage, Base):
    """Port limits, anchorages, channels, berths, terminals; GFW anchorage/dock cells (SC-05)."""

    __tablename__ = "port_zone"

    id: Mapped[UUID] = pk()
    port_id: Mapped[UUID] = fk_uuid("port.id")
    zone_type: Mapped[str] = enum_col(ZoneType, index=True)
    name: Mapped[str] = mapped_column(String(120))
    cell_id: Mapped[str | None] = mapped_column(String(64), index=True)
    geom: Mapped[Any] = geom_col("GEOMETRY")
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]
    attrs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class ExternalId(Lineage, Base):
    """SC-02: every outside identifier of an entity (UN/LOCODE, PortWatch, GFW, GeoNames, OSM,
    IMO, MMSI, GDACS, GLIDE, FDA recall …), with validity, instead of ever more ID columns."""

    __tablename__ = "external_id"
    __extra_args__ = (
        UniqueConstraint("entity_type", "scheme", "value", "entity_id"),
        Index("ix_external_id_scheme_value", "scheme", "value"),
    )

    id: Mapped[UUID] = pk()
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column(index=True)
    scheme: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(200))
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]


class Organization(Lineage, Base):
    """Firms. `name_key` lets a name pack (Q-05) swap display names without reseeding."""

    __tablename__ = "organization"

    id: Mapped[UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str | None] = mapped_column(String(80), index=True)
    country_iso2: Mapped[str | None] = mapped_column(String(2))
    kind: Mapped[str] = enum_col(OrgKind, index=True)
    industry: Mapped[str | None] = enum_col(Industry, nullable=True)
    lei: Mapped[str | None] = mapped_column(String(20))
    osh_id: Mapped[str | None] = mapped_column(String(40))
    wikidata_qid: Mapped[str | None] = mapped_column(String(20))
    is_fictional: Mapped[bool]
    name_embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    attrs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class Facility(Lineage, Base):
    __tablename__ = "facility"

    id: Mapped[UUID] = pk()
    organization_id: Mapped[UUID] = fk_uuid("organization.id")
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str | None] = mapped_column(String(80), index=True)
    facility_type: Mapped[str] = enum_col(FacilityType, index=True)
    location_id: Mapped[UUID] = fk_uuid("location.id")
    cluster: Mapped[str | None] = mapped_column(String(40), index=True)
    capacity: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    certifications: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))


class Product(Lineage, Base):
    __tablename__ = "product"
    __extra_args__ = (UniqueConstraint("sku", "scenario_id"),)

    id: Mapped[UUID] = pk()
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = enum_col(Industry, index=True)
    hs6: Mapped[str | None] = mapped_column(String(6), index=True)
    gtin: Mapped[str | None] = mapped_column(String(14))
    uom: Mapped[str] = mapped_column(String(16))
    unit_value_usd: Mapped[float | None]
    cold_chain: Mapped[bool] = mapped_column(default=False)
    temp_range_c: Mapped[list[Any] | None]
    shelf_life_days: Mapped[int | None]
    hazardous: Mapped[bool] = mapped_column(default=False)


class BomEdge(Lineage, Base):
    __tablename__ = "bom_edge"
    __extra_args__ = (CheckConstraint("qty_per_unit > 0", name="qty_positive"),)

    id: Mapped[UUID] = pk()
    parent_product_id: Mapped[UUID] = fk_uuid("product.id")
    component_product_id: Mapped[UUID] = fk_uuid("product.id")
    qty_per_unit: Mapped[float]


class Lane(Lineage, Base):
    __tablename__ = "lane"

    id: Mapped[UUID] = pk()
    origin_location_id: Mapped[UUID] = fk_uuid("location.id")
    dest_location_id: Mapped[UUID] = fk_uuid("location.id")
    mode: Mapped[str] = enum_col(TransportMode)
    via: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    distance_km: Mapped[float | None]
    typical_transit_d: Mapped[float | None]
    geom: Mapped[Any] = geom_col("MULTILINESTRING")


class SupplyEdge(Lineage, Base):
    __tablename__ = "supply_edge"
    __extra_args__ = (
        CheckConstraint("share >= 0 AND share <= 1", name="share_unit_interval"),
        CheckConstraint("lead_time_mean_d >= 0", name="lead_time_nonnegative"),
    )

    id: Mapped[UUID] = pk()
    from_facility_id: Mapped[UUID] = fk_uuid("facility.id")
    to_facility_id: Mapped[UUID] = fk_uuid("facility.id")
    product_id: Mapped[UUID] = fk_uuid("product.id")
    share: Mapped[float]
    capacity_per_week: Mapped[float | None]
    lead_time_mean_d: Mapped[float]
    lead_time_sd_d: Mapped[float | None]
    mode: Mapped[str] = enum_col(TransportMode)
    lane_id: Mapped[UUID | None] = fk_uuid("lane.id", nullable=True)
    cost_per_unit_usd: Mapped[float | None]
    is_inferred: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float | None]
    valid_from: Mapped[dt.date | None]
    valid_to: Mapped[dt.date | None]


class Holiday(Lineage, Base):
    """SC-12: public holidays plus extended closures and truck bans the package misses."""

    __tablename__ = "holiday"

    id: Mapped[UUID] = pk()
    date: Mapped[dt.date] = mapped_column(index=True)
    kind: Mapped[str] = enum_col(HolidayKind)
    name: Mapped[str] = mapped_column(String(200))
    country_iso2: Mapped[str] = mapped_column(String(2))
    notice_url: Mapped[str | None] = mapped_column(String(500))


class EmissionFactor(Lineage, Base):
    """SC-12: CO2e factors (UK DESNZ, GLEC/ISO 14083 method; A-016)."""

    __tablename__ = "emission_factor"

    id: Mapped[UUID] = pk()
    mode: Mapped[str] = enum_col(TransportMode)
    vehicle_class: Mapped[str] = mapped_column(String(200))
    fuel: Mapped[str | None] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(40))
    ghg_unit: Mapped[str] = mapped_column(String(40))
    value: Mapped[float]
    scope: Mapped[str] = mapped_column(String(16))
    year: Mapped[int]


class TradeFlow(Lineage, Base):
    """SC-11: bilateral trade by HS code; mirror flows where Bangladesh does not report."""

    __tablename__ = "trade_flow"

    id: Mapped[UUID] = pk()
    reporter_iso3: Mapped[str] = mapped_column(String(3), index=True)
    partner_iso3: Mapped[str] = mapped_column(String(3), index=True)
    hs_code: Mapped[str] = mapped_column(String(10), index=True)
    year: Mapped[int]
    flow: Mapped[str] = mapped_column(String(8))
    value_usd: Mapped[float | None]
    net_wgt_kg: Mapped[float | None]
    is_mirror: Mapped[bool] = mapped_column(default=False)


class CountryIndicator(Lineage, Base):
    """Annual country indicators (WDI, LPI, WGI, INFORM, ND-GAIN) for C1 risk features."""

    __tablename__ = "country_indicator"
    __extra_args__ = (Index("ix_country_indicator_key", "country_iso3", "indicator_code", "year"),)

    id: Mapped[UUID] = pk()
    country_iso3: Mapped[str] = mapped_column(String(3))
    indicator_code: Mapped[str] = mapped_column(String(64))
    indicator_name: Mapped[str] = mapped_column(String(300))
    year: Mapped[int]
    value: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(64))


class FxRate(Lineage, Base):
    __tablename__ = "fx_rate"
    __extra_args__ = (UniqueConstraint("date", "base", "quote", "source_id"),)

    id: Mapped[UUID] = pk()
    date: Mapped[dt.date]
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float]
