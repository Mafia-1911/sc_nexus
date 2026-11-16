"""Service layer for Universal Quality AI inspection requests."""

from __future__ import annotations

import base64
import io
import logging

import numpy as np
from PIL import Image

from cportal_c5.engine import QualityInspectionEngine
from cportal_c5.schemas import (
    CATEGORY_DOMAINS,
    DEFAULT_THRESHOLDS,
    InspectionResponse,
    InspectionVerdict,
)

logger = logging.getLogger("cportal_c5.service")


class QualityInspectionService:
    """Provides high-level inspection execution and payload formatting."""

    _engine: QualityInspectionEngine | None = None

    @classmethod
    def get_engine(cls) -> QualityInspectionEngine:
        """Return shared QualityInspectionEngine instance."""
        if cls._engine is None:
            cls._engine = QualityInspectionEngine()
        return cls._engine

    @classmethod
    def inspect(
        self,
        image: Image.Image | np.ndarray,
        category: str,
        threshold: float | None = None,
        include_base64_heatmap: bool = False,
    ) -> tuple[InspectionResponse, np.ndarray, np.ndarray]:
        """Perform end-to-end inspection and return structured response.

        Args:
            image: PIL Image or RGB numpy array.
            category: Product category ('zipper', 'capsule').
            threshold: Optional threshold override.
            include_base64_heatmap: Whether to serialize the overlay into base64.

        Returns:
            Tuple of (InspectionResponse, raw_anomaly_map, overlay_rgb_image).
        """
        category_clean = category.lower().strip()
        engine = self.get_engine()

        # Execute model inference
        score, anomaly_map, overlay_rgb, latency = engine.inspect(image, category_clean)

        # Apply thresholding
        active_threshold = (
            threshold if threshold is not None else DEFAULT_THRESHOLDS.get(category_clean, 0.40)
        )
        is_anomalous = bool(score > active_threshold)

        if is_anomalous:
            verdict = InspectionVerdict.POSSIBLE_ANOMALY
            severity = "HIGH" if score > active_threshold + 0.02 else "MEDIUM"
        else:
            verdict = InspectionVerdict.NOMINAL
            severity = "LOW"

        # Optional base64 serialization for API transport
        heatmap_b64 = None
        if include_base64_heatmap:
            overlay_pil = Image.fromarray(overlay_rgb)
            buf = io.BytesIO()
            overlay_pil.save(buf, format="PNG")
            raw_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            heatmap_b64 = f"data:image/png;base64,{raw_b64}"

        response = InspectionResponse(
            category=category_clean,
            domain=CATEGORY_DOMAINS.get(category_clean, "General Manufacturing"),
            anomaly_score=round(score, 4),
            threshold=round(active_threshold, 4),
            is_anomalous=is_anomalous,
            verdict=verdict,
            severity=severity,
            device=str(engine.device),
            latency_ms=round(latency, 1),
            heatmap_base64=heatmap_b64,
            metadata={
                "heatmap_min": round(float(anomaly_map.min()), 4),
                "heatmap_max": round(float(anomaly_map.max()), 4),
                "heatmap_mean": round(float(anomaly_map.mean()), 4),
            },
        )

        return response, anomaly_map, overlay_rgb
