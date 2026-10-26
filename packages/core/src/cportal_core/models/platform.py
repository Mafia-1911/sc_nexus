"""Scenarios, alerts, recommendations, models, predictions, sources, jobs and the outbox."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import (
    AlertStatus,
    Capability,
    JobStatus,
    RecommendationAction,
    RecommendationStatus,
    RunStatus,
    Severity,
)
from cportal_core.ids import new_id
from cportal_core.models.base import Base, Lineage, enum_col, fk_uuid, pk


class Scenario(Lineage, Base):
    """A seeded world plus disruptions. Every synthetic row carries its `scenario_id`."""

    __tablename__ = "scenario"

    id: Mapped[UUID] = pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    definition: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    seed: Mapped[int] = mapped_column(Integer)
    is_baseline: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str | None] = mapped_column(String(64))


class ScenarioResult(Lineage, Base):
    __tablename__ = "scenario_result"

    id: Mapped[UUID] = pk()
    run_scenario_id: Mapped[UUID] = fk_uuid("scenario.id", ondelete="CASCADE")
    capability: Mapped[str] = enum_col(Capability)
    kpis: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    artifacts: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class Alert(Lineage, Base):
    __tablename__ = "alert"

    id: Mapped[UUID] = pk()
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = enum_col(Severity)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    entity_refs: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    event_id: Mapped[UUID | None] = fk_uuid("disruption_event.id", nullable=True)
    status: Mapped[str] = enum_col(AlertStatus)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)


class Recommendation(Lineage, Base):
    __tablename__ = "recommendation"

    id: Mapped[UUID] = pk()
    alert_id: Mapped[UUID] = fk_uuid("alert.id", ondelete="CASCADE")
    action_type: Mapped[str] = enum_col(RecommendationAction)
    target_refs: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    expected_benefit_usd: Mapped[float | None]
    expected_cost_usd: Mapped[float | None]
    confidence: Mapped[float | None]
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    status: Mapped[str] = enum_col(RecommendationStatus)
    decided_at: Mapped[dt.datetime | None]
    feedback: Mapped[str | None] = mapped_column(Text)


class ModelVersion(Lineage, Base):
    __tablename__ = "model_version"

    id: Mapped[UUID] = pk()
    capability: Mapped[str] = enum_col(Capability)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    artifact_uri: Mapped[str | None] = mapped_column(String(500))
    card: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    licence: Mapped[str | None] = mapped_column(String(120))
    registered_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    is_active: Mapped[bool] = mapped_column(default=False)


class Prediction(Lineage, Base):
    __tablename__ = "prediction"
    __extra_args__ = (Index("ix_prediction_target", "target_type", "target_id", "as_of"),)

    id: Mapped[UUID] = pk()
    capability: Mapped[str] = enum_col(Capability)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[UUID]
    as_of: Mapped[dt.datetime]
    horizon_h: Mapped[float | None]
    value: Mapped[float | None]
    quantiles: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    dist_params: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    model_version_id: Mapped[UUID | None] = fk_uuid("model_version.id", nullable=True)
    explanation: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    features_hash: Mapped[str | None] = mapped_column(String(64))


class DataSource(Lineage, Base):
    """Mirror of `config/sources.yaml` for the Data & Models page and freshness KPIs."""

    __tablename__ = "data_source"

    id: Mapped[UUID] = pk()
    ds_id: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(24))
    default_mode: Mapped[str | None] = mapped_column(String(16))
    fallback: Mapped[str | None] = mapped_column(String(32))
    licence: Mapped[str | None] = mapped_column(Text)
    nc: Mapped[bool] = mapped_column(default=False)
    cadence: Mapped[str | None] = mapped_column(String(64))
    last_success_ts: Mapped[dt.datetime | None]
    # Runtime state for the two-strikes rule (ADR-011), written by the worker.
    last_attempt_ts: Mapped[dt.datetime | None]
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    effective_mode: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Lineage, Base):
    __tablename__ = "ingestion_run"

    id: Mapped[UUID] = pk()
    started_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[dt.datetime | None]
    status: Mapped[str] = enum_col(RunStatus)
    records: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float | None]
    notes: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class OutboxEvent(Base):
    """Infrastructure, not domain data: no lineage columns (ADR-004)."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        Index(
            "ix_outbox_event_pending", "created_at", postgresql_where=text("processed_at IS NULL")
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[dt.datetime | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    """`POST …/jobs` returns 202 + job id; clients poll `GET /jobs/{id}` (04 §7)."""

    __tablename__ = "job"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    status: Mapped[str] = enum_col(JobStatus)
    progress: Mapped[float] = mapped_column(default=0.0)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[dt.datetime | None]
    finished_at: Mapped[dt.datetime | None]
