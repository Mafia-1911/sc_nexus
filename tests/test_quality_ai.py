"""Unit and integration tests for Universal Quality AI (C5)."""

from __future__ import annotations

import io
import math
from pathlib import Path
import sys

# Ensure packages are on path
repo_root = Path(__file__).resolve().parent.parent
c5_src = repo_root / "packages" / "c5_quality" / "src"
core_src = repo_root / "packages" / "core" / "src"
api_src = repo_root / "apps" / "api" / "src"

for p in (c5_src, core_src, api_src):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from PIL import Image
import pytest
from starlette.testclient import TestClient

from cportal_c5.engine import QualityInspectionEngine
from cportal_c5.schemas import (
    DEFAULT_THRESHOLDS,
    InspectionResponse,
    InspectionVerdict,
    SupportedCategory,
)
from cportal_c5.service import QualityInspectionService


@pytest.fixture(scope="module")
def sample_image() -> Image.Image:
    """Load or generate a real test sample image."""
    img_path = repo_root / "data" / "samples" / "quality" / "zipper_good.png"
    if img_path.exists():
        return Image.open(img_path).convert("RGB")
    # Fallback synthetic texture if sample path is absent
    return Image.new("RGB", (240, 240), color=(128, 128, 128))


def test_quality_schemas() -> None:
    """Verify that schemas and default thresholds are properly structured."""
    assert "zipper" in DEFAULT_THRESHOLDS
    assert "capsule" in DEFAULT_THRESHOLDS
    assert 0.2 < DEFAULT_THRESHOLDS["zipper"] < 0.6
    assert 0.2 < DEFAULT_THRESHOLDS["capsule"] < 0.6
    assert SupportedCategory.ZIPPER.value == "zipper"
    assert SupportedCategory.CAPSULE.value == "capsule"


def test_quality_engine_initialization() -> None:
    """Verify that the QualityInspectionEngine initializes on a valid device."""
    engine = QualityInspectionEngine()
    assert str(engine.device) in ("cpu", "cuda")
    assert engine.input_size == (240, 240)


def test_quality_service_inference(sample_image: Image.Image) -> None:
    """Verify that the service executes zero-shot inference and returns valid metrics."""
    resp, anomaly_map, overlay = QualityInspectionService.inspect(
        image=sample_image,
        category="zipper",
        threshold=0.415,
        include_base64_heatmap=True,
    )

    assert isinstance(resp, InspectionResponse)
    assert resp.category == "zipper"
    assert math.isfinite(resp.anomaly_score)
    assert resp.verdict in (InspectionVerdict.NOMINAL, InspectionVerdict.POSSIBLE_ANOMALY)
    assert anomaly_map.ndim == 2
    assert overlay.ndim == 3 and overlay.shape[2] == 3
    assert resp.heatmap_base64 is not None
    assert len(resp.heatmap_base64) > 100


def test_quality_api_info_endpoint() -> None:
    """Verify that GET /api/v1/quality/info returns metadata and categories."""
    from cportal_api.main import app

    client = TestClient(app)
    res = client.get("/api/v1/quality/info")
    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["model"] == "WinCLIP (OpenAI ViT-B/16+ / Intel Anomalib)"
    assert "zipper" in body["data"]["supported_categories"]
    assert "capsule" in body["data"]["supported_categories"]


def test_quality_api_inspect_endpoint(sample_image: Image.Image) -> None:
    """Verify that POST /api/v1/quality/inspect accepts multipart image and returns verdict."""
    from cportal_api.main import app

    client = TestClient(app)

    buf = io.BytesIO()
    sample_image.save(buf, format="PNG")
    buf.seek(0)

    res = client.post(
        "/api/v1/quality/inspect",
        files={"file": ("test.png", buf, "image/png")},
        data={"category": "zipper", "threshold": "0.415"},
    )

    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    data = body["data"]
    assert data["category"] == "zipper"
    assert "anomaly_score" in data
    assert math.isfinite(data["anomaly_score"])
    assert "verdict" in data
    assert "heatmap_base64" in data
    assert data["heatmap_base64"] is not None
