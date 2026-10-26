"""News articles and disruption events with evidence (mostly C2)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import AlertLevel, DiscoveredVia, DisruptionType, EventStatus, LinkMethod
from cportal_core.models.base import EMBEDDING_DIM, Base, Lineage, enum_col, fk_uuid, geom_col, pk


class Article(Lineage, Base):
    """News copyright guardrail (03 §5): URL, title and a ≤ 300-character snippet only."""

    __tablename__ = "article"
    __extra_args__ = (
        CheckConstraint("char_length(snippet) <= 300", name="snippet_max_300"),
        Index(
            "ix_article_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = pk()
    url: Mapped[str] = mapped_column(String(2000))
    url_canonical: Mapped[str] = mapped_column(String(2000), index=True)
    source_name: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[dt.datetime | None] = mapped_column(index=True)
    lang: Mapped[str | None] = mapped_column(String(8))
    source_lang: Mapped[str | None] = mapped_column(String(8))  # SC-10 (GKG srclc)
    title: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(String(300))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    discovered_via: Mapped[str] = enum_col(DiscoveredVia)  # SC-10
    feed_id: Mapped[str | None] = mapped_column(String(64))  # SC-10
    gdelt_ids: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    themes: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    locations: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    tone: Mapped[float | None]
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class DisruptionEvent(Lineage, Base):
    __tablename__ = "disruption_event"
    __extra_args__ = (
        CheckConstraint("severity IS NULL OR severity BETWEEN 0 AND 1", name="severity_unit"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_unit"),
        Index("ix_disruption_event_locodes", "locodes", postgresql_using="gin"),
    )

    id: Mapped[UUID] = pk()
    type: Mapped[str] = enum_col(DisruptionType, index=True)
    subtype: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = enum_col(EventStatus)
    severity: Mapped[float | None]
    confidence: Mapped[float | None]
    alert_level: Mapped[str | None] = enum_col(AlertLevel, nullable=True)  # SC-09
    start_est: Mapped[dt.datetime | None] = mapped_column(index=True)
    start_uncertainty_h: Mapped[float | None]
    end_est: Mapped[dt.datetime | None]
    duration_p50_h: Mapped[float | None]
    duration_p90_h: Mapped[float | None]
    geom: Mapped[Any] = geom_col("GEOMETRY")
    locodes: Mapped[list[str]] = mapped_column(
        ARRAY(String(5)), default=list, server_default=text("'{}'")
    )
    country_iso3: Mapped[list[str]] = mapped_column(
        ARRAY(String(3)), default=list, server_default=text("'{}'")
    )
    first_seen: Mapped[dt.datetime | None]
    last_updated: Mapped[dt.datetime | None]
    cluster_key: Mapped[str | None] = mapped_column(String(128), index=True)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'")
    )  # SC-09
    url: Mapped[str | None] = mapped_column(String(2000))


class EventMention(Lineage, Base):
    __tablename__ = "event_mention"

    id: Mapped[UUID] = pk()
    event_id: Mapped[UUID] = fk_uuid("disruption_event.id", ondelete="CASCADE")
    article_id: Mapped[UUID] = fk_uuid("article.id", ondelete="CASCADE")
    extracted: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    evidence_spans: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'")
    )
    extractor_version: Mapped[str | None] = mapped_column(String(64))
    extraction_confidence: Mapped[float | None]


class EventEntityLink(Lineage, Base):
    __tablename__ = "event_entity_link"

    id: Mapped[UUID] = pk()
    event_id: Mapped[UUID] = fk_uuid("disruption_event.id", ondelete="CASCADE")
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID] = mapped_column(index=True)
    link_method: Mapped[str] = enum_col(LinkMethod)
    link_confidence: Mapped[float | None]
    impact_hint: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
