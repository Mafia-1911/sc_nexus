"""C3's road network (DS-GEO-01): OSM edges between junctions in the corridor box."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.models.base import Base, Lineage, geom_col, pk


class RoadEdge(Lineage, Base):
    __tablename__ = "road_edge"

    id: Mapped[UUID] = pk()
    way_id: Mapped[int] = mapped_column(BigInteger)
    u: Mapped[int] = mapped_column(BigInteger, index=True)
    v: Mapped[int] = mapped_column(BigInteger, index=True)
    length_m: Mapped[float] = mapped_column(Float)
    highway: Mapped[str] = mapped_column(String(32))
    oneway: Mapped[bool] = mapped_column(default=False)
    maxspeed_kmh: Mapped[float | None]
    name: Mapped[str | None] = mapped_column(String(200))
    geom: Mapped[Any] = geom_col("LINESTRING", nullable=False)
