"""Production batches, inspection images and results (C5)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.enums import BatchStatus, ImageSplit, Severity
from cportal_core.models.base import Base, Lineage, enum_col, fk_uuid, pk


class ImageDataset(Lineage, Base):
    """Provenance of inspection images: which open dataset, under which licence (rule 9)."""

    __tablename__ = "image_dataset"

    id: Mapped[UUID] = pk()
    dataset_ref: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(300))
    licence: Mapped[str | None] = mapped_column(String(120))
    nc: Mapped[bool] = mapped_column(default=False)
    url: Mapped[str | None] = mapped_column(String(500))
    task: Mapped[str] = mapped_column(String(40))
    categories: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    classes: Mapped[list[Any]] = mapped_column(default=list, server_default=text("'[]'"))
    n_images: Mapped[int | None]
    splits: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    size_bytes: Mapped[int | None]


class Batch(Lineage, Base):
    __tablename__ = "batch"
    __extra_args__ = (CheckConstraint("size_units > 0", name="size_positive"),)

    id: Mapped[UUID] = pk()
    lot_code: Mapped[str] = mapped_column(String(40), index=True)
    product_id: Mapped[UUID] = fk_uuid("product.id")
    facility_id: Mapped[UUID] = fk_uuid("facility.id")
    supplier_facility_id: Mapped[UUID | None] = fk_uuid("facility.id", nullable=True)
    line: Mapped[str | None] = mapped_column(String(16))
    shift: Mapped[str | None] = mapped_column(String(8))
    size_units: Mapped[int] = mapped_column(Integer)
    produced_at: Mapped[dt.datetime]
    status: Mapped[str] = enum_col(BatchStatus)
    aql_level: Mapped[str | None] = mapped_column(String(16))
    aql_result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))


class InspectionImage(Lineage, Base):
    """Always a real dataset image (03 §4), mapped to a fictional SKU and batch when used."""

    __tablename__ = "inspection_image"

    id: Mapped[UUID] = pk()
    dataset_id: Mapped[UUID | None] = fk_uuid("image_dataset.id", nullable=True)
    batch_id: Mapped[UUID | None] = fk_uuid("batch.id", nullable=True)
    product_id: Mapped[UUID | None] = fk_uuid("product.id", nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    split: Mapped[str | None] = enum_col(ImageSplit, nullable=True)
    label: Mapped[str | None] = mapped_column(String(64))
    uri: Mapped[str] = mapped_column(String(500))
    mask_uri: Mapped[str | None] = mapped_column(String(500))
    width: Mapped[int | None]
    height: Mapped[int | None]
    captured_at: Mapped[dt.datetime | None]
    source_dataset: Mapped[str] = mapped_column(String(120))


class InspectionResult(Lineage, Base):
    __tablename__ = "inspection_result"

    id: Mapped[UUID] = pk()
    image_id: Mapped[UUID] = fk_uuid("inspection_image.id", ondelete="CASCADE")
    model_version_id: Mapped[UUID | None] = fk_uuid("model_version.id", nullable=True)
    image_score: Mapped[float]
    is_anomalous: Mapped[bool]
    threshold: Mapped[float]
    defect_type: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = enum_col(Severity, nullable=True)
    heatmap_uri: Mapped[str | None] = mapped_column(String(500))
    mask_uri: Mapped[str | None] = mapped_column(String(500))
    latency_ms: Mapped[float | None]
