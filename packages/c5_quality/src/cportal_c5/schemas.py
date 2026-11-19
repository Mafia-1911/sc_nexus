"""Data schemas for Universal Quality AI (C5) inspection engine."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SupportedCategory(str, Enum):
    """Supported product categories for zero-shot inspection."""

    ZIPPER = "zipper"
    CAPSULE = "capsule"


CATEGORY_DOMAINS: dict[str, str] = {
    "zipper": "Garments & Apparel Hardware",
    "capsule": "Pharmaceuticals & Healthcare",
}

# Empirical default baseline thresholds calibrated from MVTec AD samples.
# Note: Raw scores are uncalibrated cosine similarities; thresholds provide
# an operational guideline for screening, not absolute probability.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "zipper": 0.415,
    "capsule": 0.320,
}


class InspectionVerdict(str, Enum):
    """Screening verdict for inspected sample."""

    NOMINAL = "NOMINAL — No Significant Anomaly Detected"
    POSSIBLE_ANOMALY = "POSSIBLE ANOMALY — Flagged for QA Review"


class InspectionRequest(BaseModel):
    """Request payload for quality inspection."""

    category: SupportedCategory = Field(
        default=SupportedCategory.ZIPPER,
        description="Target product category for zero-shot prompt ensembling",
    )
    threshold: float | None = Field(
        default=None,
        description="Optional custom anomaly threshold override. If None, default calibrated baseline is used.",
    )


class InspectionResponse(BaseModel):
    """Detailed response schema for an inspection event."""

    category: str
    domain: str
    anomaly_score: float
    threshold: float
    is_anomalous: bool
    verdict: InspectionVerdict
    severity: str
    model_name: str = "WinCLIP (OpenAI ViT-B/16+)"
    model_mode: str = "Zero-Shot (k_shot=0, no target training images)"
    device: str
    latency_ms: float
    heatmap_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "Visual anomaly screening provided for QA assistance only. "
        "Pharmaceutical inspections must be confirmed by a qualified human QA officer; "
        "not intended as autonomous regulatory release."
    )
