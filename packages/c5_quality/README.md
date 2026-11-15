# `cportal-c5`: Manufacturing Defect Intelligence (Universal Quality AI)

`cportal-c5` provides zero-shot visual anomaly detection and defect localization for Supply Chain Nexus (ShipperFast), targeting export manufacturing quality control on the Chattogram–Dhaka corridor.

## Key Capabilities

1. **Zero-Shot Anomaly Detection (`k_shot=0`)**:
   - Powered by Intel Anomalib and OpenAI CLIP ViT-B/16+ (pretrained on `laion400m_e31`).
   - Requires **no prior defect training images**. Uses compositional prompt templates (e.g., `["a photo of a {}", "a photo of a defective {}"]`) combined with state, defect, and texture modifiers.
2. **Defect Localization (Pixel Heatmaps)**:
   - Multiscale window-based visual tokens (WinCLIP) yield a 2D anomaly probability map.
   - Outputs both raw 2D normalized float maps and JET colormap RGB overlays.
3. **Product Domain Coverage**:
   - **Garments & Apparel Hardware**: Evaluated on MVTec AD `zipper` (broken teeth, fabric split, rough surfaces). Baseline calibrated screening threshold: `0.4150`.
   - **Pharmaceuticals & Healthcare**: Evaluated on MVTec AD `capsule` (cracks, scratches, dents). Baseline calibrated screening threshold: `0.3200`.
4. **Deterministic CPU & Edge Execution**:
   - Runs cleanly and deterministically on CPU to avoid platform-dependent tensor convolution bugs.
   - Evaluates in ~1.5s per image on standard laptop processors with cached prompt embeddings.

> **Visual Screening Notice**: Visual defect detection provides early operational screening and QA prioritization. It is not an automated replacement for ISO-certified pharmaceutical lot release or GMP testing protocols.

---

## Architecture & Code Structure

```
packages/c5_quality/
├── pyproject.toml              # Package metadata and dependencies (cportal-c5)
├── README.md                   # This documentation
└── src/
    └── cportal_c5/
        ├── __init__.py         # Public exports (schemas, engine, service)
        ├── schemas.py          # Typed Pydantic models (SupportedCategory, InspectionVerdict, etc.)
        ├── engine.py           # Core QualityInspectionEngine wrapping Anomalib WinClip
        └── service.py          # QualityInspectionService orchestrating inference & base64 encoding
```

---

## Python Usage Example

```python
from PIL import Image
from cportal_c5.service import QualityInspectionService

# Load image
img = Image.open("data/samples/quality/zipper_defect.png")

# Run zero-shot inspection
response, anomaly_map, overlay = QualityInspectionService.inspect(
    image=img,
    category="zipper",
    threshold=0.415,
    include_base64_heatmap=True,
)

print(f"Anomaly Score: {response.anomaly_score:.4f}")
print(f"Verdict: {response.verdict}")
print(f"Severity: {response.severity}")
print(f"Latency: {response.latency_ms:.1f}ms")
```

---

## Testing & Verification

```bash
# Run unit and API tests
uv run pytest tests/test_quality_ai.py -v

# Run visual smoke test on genuine MVTec AD samples
uv run python scripts/run_quality_smoke_test.py
```
