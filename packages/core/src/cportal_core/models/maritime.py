"""Vessels, AIS, port calls, port state, satellite and weather observations (mostly C4)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import (
    PortCallMethod,
    PortCallStatus,
    SatelliteSensor,
    ShipTypeGroup,
    VisitKind,
    WeatherKind,
)
from cportal_core.models.base import Base, Lineage, enum_col, fk_uuid, geom_col, pk


class Vessel(Lineage, Base):
    """IMO when known; MMSI can change and be reused, so history lives in `vessel_identity`."""

    __tablename__ = "vessel"
    __extra_args__ = (
        Index(
            "uq_vessel_imo_scope",
            "imo",
            text("coalesce(scenario_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("imo IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = pk()
    imo: Mapped[str | None] = mapped_column(String(7))
    mmsi: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    call_sign: Mapped[str | None] = mapped_column(String(16))
    ship_type_ais: Mapped[int | None] = mapped_column(SmallInteger)
    ship_type_group: Mapped[str | None] = enum_col(ShipTypeGroup, nullable=True, index=True)
    loa_m: Mapped[float | None]
    beam_m: Mapped[float | None]
    dwt: Mapped[float | None]
    gt: Mapped[float | None]
    flag_iso3: Mapped[str | None] = mapped_column(String(3))  # SC-08


class VesselIdentity(Lineage, Base):
    __tablename__ = "vessel_identity"

    id: Mapped[UUID] = pk()
    vessel_id: Mapped[UUID] = fk_uuid("vessel.id", ondelete="CASCADE")
    mmsi: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    call_sign: Mapped[str | None] = mapped_column(String(16))
    flag_iso3: Mapped[str | None] = mapped_column(String(3))
    valid_from: Mapped[dt.datetime | None]
    valid_to: Mapped[dt.datetime | None]


class AisPositionLatest(Lineage, Base):
    """Latest position per vessel; the full history is Parquet in the lake (ADR-003)."""

    __tablename__ = "ais_position_latest"

    id: Mapped[UUID] = pk()
    vessel_id: Mapped[UUID | None] = fk_uuid("vessel.id", nullable=True)
    mmsi: Mapped[int] = mapped_column(BigInteger, index=True)
    ts: Mapped[dt.datetime] = mapped_column(index=True)
    received_at: Mapped[dt.datetime | None]  # SC-08
    msg_type: Mapped[str | None] = mapped_column(String(40))
    geom: Mapped[Any] = geom_col("POINT", nullable=False)
    sog_kn: Mapped[float | None]
    cog_deg: Mapped[float | None]
    heading_deg: Mapped[float | None]
    nav_status: Mapped[int | None] = mapped_column(SmallInteger)
    draught_m: Mapped[float | None]
    destination: Mapped[str | None] = mapped_column(String(40))
    eta_reported: Mapped[dt.datetime | None]


class PortCall(Lineage, Base):
    """One vessel visit. D-04: vessel dwell = anchorage wait + berth time; for anchorage-only
    visits (lighterage, SC-03) dwell is the whole stay and berth time is null."""

    __tablename__ = "port_call"
    __extra_args__ = (
        CheckConstraint("dwell_h IS NULL OR dwell_h >= 0", name="dwell_nonnegative"),
        CheckConstraint(
            "berth_start_ts IS NULL OR anchorage_start_ts IS NULL "
            "OR berth_start_ts >= anchorage_start_ts",
            name="berth_after_anchorage",
        ),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 1 AND 4", name="confidence"),
        Index("ix_port_call_port_arrival", "port_id", "arrival_ts"),
    )

    id: Mapped[UUID] = pk()
    vessel_id: Mapped[UUID] = fk_uuid("vessel.id")
    port_id: Mapped[UUID] = fk_uuid("port.id")
    status: Mapped[str] = enum_col(PortCallStatus)
    visit_kind: Mapped[str | None] = enum_col(VisitKind, nullable=True)
    arrival_ts: Mapped[dt.datetime | None]
    anchorage_start_ts: Mapped[dt.datetime | None]
    anchorage_end_ts: Mapped[dt.datetime | None]
    berth_start_ts: Mapped[dt.datetime | None]
    berth_end_ts: Mapped[dt.datetime | None]
    departure_ts: Mapped[dt.datetime | None]
    departure_planned_ts: Mapped[dt.datetime | None]
    waiting_h: Mapped[float | None]
    berth_h: Mapped[float | None]
    dwell_h: Mapped[float | None]
    berth_zone_id: Mapped[UUID | None] = fk_uuid("port_zone.id", nullable=True)
    censored: Mapped[bool] = mapped_column(default=False)
    method: Mapped[str] = enum_col(PortCallMethod)
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    gfw_visit_id: Mapped[str | None] = mapped_column(String(64), index=True)
    quality_flags: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))


class PortCallStop(Lineage, Base):
    """SC-03: the anchorage and dock cells a visit passed through, in order."""

    __tablename__ = "port_call_stop"

    id: Mapped[UUID] = pk()
    port_call_id: Mapped[UUID] = fk_uuid("port_call.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    cell_id: Mapped[str | None] = mapped_column(String(64))
    zone_id: Mapped[UUID | None] = fk_uuid("port_zone.id", nullable=True)
    at_dock: Mapped[bool] = mapped_column(default=False)
    geom: Mapped[Any] = geom_col("POINT")
    start_ts: Mapped[dt.datetime | None]
    end_ts: Mapped[dt.datetime | None]


class PortStateSnapshot(Lineage, Base):
    __tablename__ = "port_state_snapshot"
    __extra_args__ = (Index("ix_port_state_snapshot_port_ts", "port_id", "ts"),)

    id: Mapped[UUID] = pk()
    port_id: Mapped[UUID] = fk_uuid("port.id")
    ts: Mapped[dt.datetime]
    queue_by_type: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    berth_occupancy: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'")
    )
    arrivals_24h: Mapped[int | None]
    departures_24h: Mapped[int | None]
    mean_wait_h_24h: Mapped[float | None]
    weather: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    tide: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    sar_count: Mapped[int | None]
    sar_age_h: Mapped[float | None]


class PortActivityDaily(Lineage, Base):
    """SC-06: daily port calls and trade volumes (PortWatch since 2019)."""

    __tablename__ = "port_activity_daily"
    __extra_args__ = (Index("ix_port_activity_daily_port_date", "port_id", "date"),)

    id: Mapped[UUID] = pk()
    port_id: Mapped[UUID] = fk_uuid("port.id")
    date: Mapped[dt.date]
    calls_total: Mapped[int | None]
    calls_by_type: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    import_t: Mapped[float | None]
    export_t: Mapped[float | None]
    trade_by_type: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class ZonePresenceDaily(Lineage, Base):
    """SC-07: vessel-days in a zone (GFW 4Wings presence), the real queue-length signal."""

    __tablename__ = "zone_presence_daily"
    __extra_args__ = (Index("ix_zone_presence_daily_zone_date", "zone_id", "date"),)

    id: Mapped[UUID] = pk()
    zone_id: Mapped[UUID | None] = fk_uuid("port_zone.id", nullable=True)
    area_name: Mapped[str] = mapped_column(String(64))
    date: Mapped[dt.date]
    vessel_id: Mapped[UUID | None] = fk_uuid("vessel.id", nullable=True)
    mmsi: Mapped[int | None] = mapped_column(BigInteger)
    imo: Mapped[str | None] = mapped_column(String(7))
    ship_type_group: Mapped[str | None] = enum_col(ShipTypeGroup, nullable=True)
    hours: Mapped[float]
    mean_sog_kn: Mapped[float | None]
    entry_ts: Mapped[dt.datetime | None]
    exit_ts: Mapped[dt.datetime | None]


class SatelliteObservation(Lineage, Base):
    __tablename__ = "satellite_observation"

    id: Mapped[UUID] = pk()
    sensor: Mapped[str] = enum_col(SatelliteSensor)
    scene_id: Mapped[str | None] = mapped_column(String(120))
    acq_ts: Mapped[dt.datetime] = mapped_column(index=True)
    area_name: Mapped[str | None] = mapped_column(String(64))
    zone_id: Mapped[UUID | None] = fk_uuid("port_zone.id", nullable=True)
    footprint: Mapped[Any] = geom_col("POLYGON")
    asset_href: Mapped[str | None] = mapped_column(String(500))
    cloud_pct: Mapped[float | None]
    detections_count: Mapped[int | None]
    detections: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))


class WeatherObservation(Lineage, Base):
    """Hourly weather and marine values at a point (Open-Meteo forecast, archive, marine)."""

    __tablename__ = "weather_observation"
    __extra_args__ = (Index("ix_weather_observation_point_ts", "point_name", "ts"),)

    id: Mapped[UUID] = pk()
    point_name: Mapped[str] = mapped_column(String(64))
    location_id: Mapped[UUID | None] = fk_uuid("location.id", nullable=True)
    geom: Mapped[Any] = geom_col("POINT")
    ts: Mapped[dt.datetime]
    kind: Mapped[str] = enum_col(WeatherKind)
    issued_at: Mapped[dt.datetime | None]
    temperature_2m_c: Mapped[float | None]
    precipitation_mm: Mapped[float | None]
    wind_speed_10m_kmh: Mapped[float | None]
    wind_gusts_10m_kmh: Mapped[float | None]
    wind_direction_10m_deg: Mapped[float | None]
    pressure_msl_hpa: Mapped[float | None]
    wave_height_m: Mapped[float | None]
    wave_period_s: Mapped[float | None]
    swell_wave_height_m: Mapped[float | None]
    sea_level_height_msl_m: Mapped[float | None]
    ocean_current_velocity_kmh: Mapped[float | None]
