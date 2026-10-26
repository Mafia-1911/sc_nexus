"""Declarative base, column helpers and the lineage mixin shared by every table (04 §4).

Conventions:
- UUID primary keys; deterministic UUIDv5 where a natural key exists (`cportal_core.ids`).
- Enums are VARCHAR (no Postgres ENUM types); values are validated by the Pydantic records at
  every boundary (connectors, sim, API).
- Geometry is PostGIS `geometry` in SRID 4326; distance queries cast to `geography` (ADR-002).
- Unit suffixes in column names (`_h`, `_km`, `_kn`, `_m`, `_t`, `_usd`, …).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from cportal_core.enums import DataMode
from cportal_core.ids import new_id

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EMBEDDING_DIM = 384  # small sentence-transformer class (ADR-008 revisits the model choice)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {  # noqa: RUF012 (SQLAlchemy reads this class attribute)
        datetime: DateTime(timezone=True),
        date: Date(),
        dict[str, Any]: JSONB(),
        list[Any]: JSONB(),
        UUID: Uuid(),
        bool: Boolean(),
    }


def enum_col(enum: type[StrEnum], *, nullable: bool = False, **kw: Any) -> Any:
    """A VARCHAR column holding a StrEnum's value."""
    length = max(len(m.value) for m in enum)
    return mapped_column(String(max(length, 8)), nullable=nullable, **kw)


def geom_col(kind: str = "GEOMETRY", *, nullable: bool = True) -> Any:
    """PostGIS geometry in WGS84 with a GiST index (created by GeoAlchemy2)."""
    return mapped_column(Geometry(kind, srid=4326, spatial_index=True), nullable=nullable)


def pk() -> Any:
    return mapped_column(primary_key=True, default=new_id, server_default=text("gen_random_uuid()"))


def fk_uuid(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


class Lineage:
    """Lineage columns on every domain table (04 §4 plus SC-01 `available_at`).

    `available_at` is when the fact became available to us (publication time). Point-in-time
    features filter on it, never on event time, so a backtest cannot peek past `as_of`.
    """

    source_id: Mapped[str] = mapped_column(String(32), index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(256))
    # `data_mode`, not the brief's `mode`: lane, supply_edge and shipment_leg have a transport
    # `mode` column, and one name cannot mean both (ADR-012).
    data_mode: Mapped[str] = enum_col(DataMode)
    is_synthetic: Mapped[bool] = mapped_column(default=False, index=True)
    scenario_id: Mapped[UUID | None] = mapped_column(index=True)
    generator_version: Mapped[str | None] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    available_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Subclasses add their own indexes and constraints here; the lineage check is appended.
    __extra_args__: tuple[Any, ...] = ()

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return (
            *cls.__extra_args__,
            CheckConstraint(
                "is_synthetic = (data_mode = 'synthetic')", name="lineage_synthetic_matches_mode"
            ),
            CheckConstraint(
                "(NOT is_synthetic) OR scenario_id IS NOT NULL", name="lineage_synthetic_scenario"
            ),
        )


LINEAGE_COLUMNS = (
    "source_id",
    "source_record_id",
    "data_mode",
    "is_synthetic",
    "scenario_id",
    "generator_version",
    "ingested_at",
    "available_at",
    "created_at",
    "updated_at",
)
