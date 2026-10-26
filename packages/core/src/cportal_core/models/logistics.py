"""Orders, inventory, shipments (DCSA events) and route planning (core, C3, Nexus)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import (
    CargoProfile,
    EventClassifier,
    OrderStatus,
    ShipmentStatus,
    TransportEventType,
    TransportMode,
)
from cportal_core.models.base import Base, Lineage, enum_col, fk_uuid, geom_col, pk


class CustomerOrder(Lineage, Base):
    __tablename__ = "customer_order"
    __extra_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    id: Mapped[UUID] = pk()
    reference: Mapped[str] = mapped_column(String(40), index=True)
    buyer_org_id: Mapped[UUID] = fk_uuid("organization.id")
    product_id: Mapped[UUID] = fk_uuid("product.id")
    facility_id: Mapped[UUID | None] = fk_uuid("facility.id", nullable=True)
    qty: Mapped[float]
    due_date: Mapped[dt.date] = mapped_column(index=True)
    incoterm: Mapped[str | None] = mapped_column(String(3))
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = enum_col(OrderStatus)
    revenue_usd: Mapped[float | None]


class InventoryPosition(Lineage, Base):
    __tablename__ = "inventory_position"
    __extra_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_nonnegative"),
        Index("ix_inventory_position_key", "facility_id", "product_id", "ts"),
    )

    id: Mapped[UUID] = pk()
    facility_id: Mapped[UUID] = fk_uuid("facility.id")
    product_id: Mapped[UUID] = fk_uuid("product.id")
    ts: Mapped[dt.datetime]
    on_hand: Mapped[float]
    on_order: Mapped[float] = mapped_column(default=0.0)
    allocated: Mapped[float] = mapped_column(default=0.0)
    safety_stock: Mapped[float | None]
    reorder_point: Mapped[float | None]
    days_of_cover: Mapped[float | None]


class Shipment(Lineage, Base):
    __tablename__ = "shipment"

    id: Mapped[UUID] = pk()
    reference: Mapped[str] = mapped_column(String(40), index=True)
    mode_chain: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    origin_location_id: Mapped[UUID] = fk_uuid("location.id")
    dest_location_id: Mapped[UUID] = fk_uuid("location.id")
    containers: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    cargo_profile: Mapped[str] = enum_col(CargoProfile)
    planned_eta: Mapped[dt.datetime | None]
    predicted_eta_p50: Mapped[dt.datetime | None]
    predicted_eta_p90: Mapped[dt.datetime | None]
    status: Mapped[str] = enum_col(ShipmentStatus)


class ShipmentOrder(Lineage, Base):
    """Shipment *─* Order."""

    __tablename__ = "shipment_order"
    __extra_args__ = (UniqueConstraint("shipment_id", "order_id"),)

    id: Mapped[UUID] = pk()
    shipment_id: Mapped[UUID] = fk_uuid("shipment.id", ondelete="CASCADE")
    order_id: Mapped[UUID] = fk_uuid("customer_order.id", ondelete="CASCADE")
    qty: Mapped[float | None]


class ShipmentLeg(Lineage, Base):
    __tablename__ = "shipment_leg"
    __extra_args__ = (UniqueConstraint("shipment_id", "seq"),)

    id: Mapped[UUID] = pk()
    shipment_id: Mapped[UUID] = fk_uuid("shipment.id", ondelete="CASCADE")
    seq: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = enum_col(TransportMode)
    from_location_id: Mapped[UUID] = fk_uuid("location.id")
    to_location_id: Mapped[UUID] = fk_uuid("location.id")
    vessel_id: Mapped[UUID | None] = fk_uuid("vessel.id", nullable=True)
    planned_dep: Mapped[dt.datetime | None]
    planned_arr: Mapped[dt.datetime | None]
    actual_dep: Mapped[dt.datetime | None]
    actual_arr: Mapped[dt.datetime | None]
    route_option_id: Mapped[UUID | None] = fk_uuid("route_option.id", nullable=True)


class TransportEvent(Lineage, Base):
    """DCSA Track & Trace event (TRANSPORT/EQUIPMENT/SHIPMENT; PLN/EST/ACT)."""

    __tablename__ = "transport_event"
    __extra_args__ = (Index("ix_transport_event_shipment_ts", "shipment_id", "event_ts"),)

    id: Mapped[UUID] = pk()
    shipment_id: Mapped[UUID] = fk_uuid("shipment.id", ondelete="CASCADE")
    event_type: Mapped[str] = enum_col(TransportEventType)
    classifier: Mapped[str] = enum_col(EventClassifier)
    event_code: Mapped[str] = mapped_column(String(8))
    location_id: Mapped[UUID | None] = fk_uuid("location.id", nullable=True)
    event_ts: Mapped[dt.datetime]
    vessel_id: Mapped[UUID | None] = fk_uuid("vessel.id", nullable=True)
    equipment_reference: Mapped[str | None] = mapped_column(String(11))


class RouteRequest(Lineage, Base):
    __tablename__ = "route_request"

    id: Mapped[UUID] = pk()
    origin_location_id: Mapped[UUID] = fk_uuid("location.id")
    dest_location_id: Mapped[UUID] = fk_uuid("location.id")
    cargo_profile: Mapped[str] = enum_col(CargoProfile)
    deadline: Mapped[dt.datetime | None]
    constraints: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    weights: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class RouteOption(Lineage, Base):
    __tablename__ = "route_option"

    id: Mapped[UUID] = pk()
    request_id: Mapped[UUID] = fk_uuid("route_request.id", ondelete="CASCADE")
    legs: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    geom: Mapped[Any] = geom_col("MULTILINESTRING")
    time_p50_h: Mapped[float | None]
    time_p90_h: Mapped[float | None]
    cost_bdt: Mapped[float | None]
    cost_usd: Mapped[float | None]
    co2e_kg: Mapped[float | None]
    on_time_prob: Mapped[float | None]
    pareto_rank: Mapped[int | None]
    explanation: Mapped[str | None] = mapped_column(Text)
