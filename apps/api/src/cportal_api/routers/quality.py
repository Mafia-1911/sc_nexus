"""/quality: Universal Quality AI inspection endpoints (C5)."""

from __future__ import annotations

import io
from pathlib import Path
import sys

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

# Ensure packages/c5_quality/src is accessible
repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
c5_src = repo_root / "packages" / "c5_quality" / "src"
if str(c5_src) not in sys.path:
    sys.path.insert(0, str(c5_src))

from cportal_c5.schemas import (
    CATEGORY_DOMAINS,
    DEFAULT_THRESHOLDS,
    InspectionResponse,
    SupportedCategory,
)
from cportal_c5.service import QualityInspectionService

from datetime import UTC, datetime

from cportal_api.schemas import Envelope, Meta

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/info", response_model=Envelope[dict])
def get_quality_info() -> Envelope[dict]:
    """Return model architecture and supported category metadata."""
    engine = QualityInspectionService.get_engine()
    data = {
        "capability": "C5 Manufacturing Defect Intelligence",
        "model": "WinCLIP (OpenAI ViT-B/16+ / Intel Anomalib)",
        "mode": "Zero-Shot (k_shot=0)",
        "device": str(engine.device),
        "supported_categories": [cat.value for cat in SupportedCategory],
        "category_domains": CATEGORY_DOMAINS,
        "default_thresholds": DEFAULT_THRESHOLDS,
        "source_dataset": "DS-VIS-01 (MVTec AD CC BY-NC-SA 4.0)",
    }
    return Envelope(
        data=data,
        meta=Meta(
            mode="synthetic",
            modes={"synthetic": 1},
            sources=["DS-VIS-01"],
            as_of=datetime.now(UTC),
            model_version="winclip-vit-b-16-plus-240",
            note="Zero-shot defect detection metadata",
        ),
    )


@router.post("/inspect", response_model=Envelope[InspectionResponse])
async def inspect_product_image(
    file: UploadFile = File(..., description="Product image file (PNG/JPEG)"),
    category: str = Form(
        "zipper",
        description="Target category: 'zipper' (garments) or 'capsule' (pharmaceuticals)",
    ),
    threshold: float | None = Form(
        None,
        description="Optional custom anomaly threshold override",
    ),
) -> Envelope[InspectionResponse]:
    """Run zero-shot manufacturing defect detection on an uploaded product image."""
    cat_clean = category.lower().strip()
    if cat_clean not in DEFAULT_THRESHOLDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported category '{category}'. Supported: {list(DEFAULT_THRESHOLDS.keys())}",
        )

    try:
        contents = await file.read()
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    try:
        response, _, _ = QualityInspectionService.inspect(
            image=pil_img,
            category=cat_clean,
            threshold=threshold,
            include_base64_heatmap=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inspection inference failed: {exc}") from exc

    return Envelope(
        data=response,
        meta=Meta(
            mode="synthetic",
            modes={"synthetic": 1},
            sources=["DS-VIS-01"],
            as_of=datetime.now(UTC),
            model_version="winclip-vit-b-16-plus-240",
            note=f"Zero-shot inspection for {cat_clean}",
        ),
    )
