"""C1 outputs (C1 §4): per-node graph metrics and what-if results. Written by the C1 service
(worker job or API call); derived from a scenario's world, so they carry its lineage."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import Float, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.models.base import Base, Lineage, fk_uuid, pk


class GraphMetric(Lineage, Base):
    """One row per node and scenario: dependencies, TTS/TTR, risk score and its drivers."""

    __tablename__ = "graph_metric"
    __extra_args__ = (UniqueConstraint("scenario_id", "node_id"),)

    id: Mapped[UUID] = pk()
    node_id: Mapped[str] = mapped_column(String(64), index=True)  # facility UUID or port:LOCODE
    node_kind: Mapped[str] = mapped_column(String(16))
    node_type: Mapped[str] = mapped_column(String(32))
    facility_id: Mapped[UUID | None] = fk_uuid("facility.id", nullable=True, ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(256))
    industry: Mapped[str | None] = mapped_column(String(16))
    as_of: Mapped[dt.datetime]
    downstream_products: Mapped[list[Any]] = mapped_column(
        default=list, server_default=text("'[]'")
    )
    downstream_orders: Mapped[int] = mapped_column(Integer, default=0)
    downstream_open_order_value_usd: Mapped[float] = mapped_column(Float, default=0.0)
    dominated_products: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    dominated_order_ids: Mapped[list[Any]] = mapped_column(
        default=list, server_default=text("'[]'")
    )
    dominated_orders: Mapped[int] = mapped_column(Integer, default=0)
    dominated_value_usd: Mapped[float] = mapped_column(Float, default=0.0)
    betweenness: Mapped[float] = mapped_column(Float, default=0.0)
    pagerank_rev: Mapped[float] = mapped_column(Float, default=0.0)
    hhi_inputs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    single_sourced_inputs: Mapped[list[Any]] = mapped_column(
        default=list, server_default=text("'[]'")
    )
    sole_source_for: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    tts_d: Mapped[float | None]
    tts_capped: Mapped[bool] = mapped_column(default=False)
    ttr_d: Mapped[float | None]
    ttr_p90_d: Mapped[float | None]
    ttr_source: Mapped[str | None] = mapped_column(String(16))
    performance_impact_usd: Mapped[float | None]
    risk_score: Mapped[float | None]
    risk_band: Mapped[str | None] = mapped_column(String(8))
    risk_drivers: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    features: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    model_version: Mapped[str] = mapped_column(String(64))
    inputs_fingerprint: Mapped[str | None] = mapped_column(String(64))


class WhatIfResult(Lineage, Base):
    """A cascade what-if: the request, its headline numbers and the full result document."""

    __tablename__ = "whatif_result"

    id: Mapped[UUID] = pk()
    disrupted: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    duration_d: Mapped[float]
    capacity_pct: Mapped[float]
    mc_runs: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int] = mapped_column(Integer, default=42)
    orders_late: Mapped[int] = mapped_column(Integer, default=0)
    revenue_at_risk_usd: Mapped[float] = mapped_column(Float, default=0.0)
    revenue_at_risk_usd_p50: Mapped[float | None]
    revenue_at_risk_usd_p90: Mapped[float | None]
    first_impact_d: Mapped[float | None]
    recovery_d: Mapped[float | None]
    tts_d: Mapped[float | None]
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    model_version: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[UUID | None] = fk_uuid("job.id", nullable=True, ondelete="SET NULL")
