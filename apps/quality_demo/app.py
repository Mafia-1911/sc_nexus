"""Universal Quality AI: Interactive Gradio Demo for Supply Chain Nexus (C5).

Allows inspectors and operators to upload product images, run zero-shot anomaly
detection using pretrained WinCLIP, view localization heatmaps, and inspect
screening verdicts.

Run:
    python apps/quality_demo/app.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

# Ensure packages/c5_quality/src is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
c5_src = repo_root / "packages" / "c5_quality" / "src"
if str(c5_src) not in sys.path:
    sys.path.insert(0, str(c5_src))

import gradio as gr
import numpy as np
from PIL import Image

from cportal_c5.schemas import DEFAULT_THRESHOLDS, InspectionVerdict
from cportal_c5.service import QualityInspectionService

EXAMPLES_DIR = repo_root / "data" / "samples" / "quality"


def predict_quality(
    image: Image.Image | np.ndarray | None,
    category: str,
    threshold: float,
) -> tuple[np.ndarray | None, str, str, str, str]:
    """Execute quality inspection on uploaded image.

    Returns:
        overlay_image, verdict_html, score_text, model_meta_html, disclaimer_html
    """
    if image is None:
        return (
            None,
            "<div style='color: #64748b; font-weight: bold;'>Please upload an image or select a sample below.</div>",
            "N/A",
            "N/A",
            "",
        )

    # Run C5 inspection service
    resp, _, overlay_rgb = QualityInspectionService.inspect(
        image=image,
        category=category,
        threshold=threshold,
    )

    # Format verdict badge
    if resp.verdict == InspectionVerdict.POSSIBLE_ANOMALY:
        badge_color = "#dc2626"  # red
        bg_color = "#fee2e2"
        badge_text = "POSSIBLE ANOMALY — Flagged for QA Review"
        action_note = "Action Recommended: Route to physical inspection station. Do not auto-approve lot."
    else:
        badge_color = "#16a34a"  # green
        bg_color = "#dcfce7"
        badge_text = "NOMINAL — No Significant Defect Detected"
        action_note = "Action: Within nominal screening tolerance. Proceed with standard batch handling."

    verdict_html = f"""
    <div style="background-color: {bg_color}; border: 2px solid {badge_color}; border-radius: 8px; padding: 14px; margin-bottom: 8px;">
        <div style="font-size: 1.15rem; font-weight: bold; color: {badge_color};">
            {badge_text}
        </div>
        <div style="font-size: 0.9rem; color: #334155; margin-top: 6px;">
            {action_note}
        </div>
    </div>
    """

    # Format metric score details
    score_details = f"""
### Screening Metrics:
- **Anomaly Score**: `{resp.anomaly_score:.4f}`
- **Active Threshold**: `{resp.threshold:.4f}`
- **Severity Assessment**: **{resp.severity}**
- **Inference Latency**: `{resp.latency_ms:.1f} ms`
- **Domain Focus**: *{resp.domain}*
    """

    # Format model metadata
    model_meta_html = f"""
<div style="font-size: 0.85rem; color: #475569; background: #f8fafc; border-radius: 6px; padding: 10px; border: 1px solid #e2e8f0;">
    <b>Model Architecture:</b> {resp.model_name}<br>
    <b>Operating Mode:</b> {resp.model_mode}<br>
    <b>Pretrained Weights:</b> OpenAI CLIP (laion400m_e31)<br>
    <b>Execution Device:</b> {resp.device.upper()}<br>
    <b>Spatial Resolution:</b> 240x240 multi-scale sliding windows (scales 2, 3)
</div>
    """

    disclaimer_html = f"""
<div style="font-size: 0.78rem; color: #94a3b8; margin-top: 8px;">
    ⚠️ <i>{resp.disclaimer}</i>
</div>
    """

    return overlay_rgb, verdict_html, score_details, model_meta_html, disclaimer_html


def update_threshold_default(category: str) -> float:
    """Update threshold slider default value when category changes."""
    return DEFAULT_THRESHOLDS.get(category.lower().strip(), 0.40)


def create_demo() -> gr.Blocks:
    """Build the Gradio interface."""
    with gr.Blocks(title="Universal Quality AI — Supply Chain Nexus") as demo:
        gr.Markdown(
            """
# 🔍 Universal Quality AI
### Zero-Shot Manufacturing Defect Detection · *Supply Chain Nexus (Capability C5)*

Inspect manufactured products for anomalies **without needing labeled defect images on day one**.  
Uses **WinCLIP** (Window-based CLIP) to identify anomalous visual patterns, return real continuous scores, and generate localized heatmaps.
            """
        )

        with gr.Row():
            with gr.Column(scale=5):
                gr.Markdown("### 1. Inspection Input")
                input_image = gr.Image(
                    label="Upload Product Image (or click an example below)",
                    type="pil",
                    height=360,
                )

                with gr.Row():
                    category_dropdown = gr.Dropdown(
                        choices=["zipper", "capsule"],
                        value="zipper",
                        label="Product Category",
                        info="Configures category-specific prompt ensembling (garment hardware vs pharmaceutical capsule).",
                    )
                    threshold_slider = gr.Slider(
                        minimum=0.25,
                        maximum=0.55,
                        value=DEFAULT_THRESHOLDS["zipper"],
                        step=0.005,
                        label="Screening Threshold",
                        info="Adjustable sensitivity. Items scoring above threshold are flagged for QA review.",
                    )

                category_dropdown.change(
                    fn=update_threshold_default,
                    inputs=[category_dropdown],
                    outputs=[threshold_slider],
                )

                inspect_btn = gr.Button("🔍 Run Defect Inspection", variant="primary", size="lg")

            with gr.Column(scale=5):
                gr.Markdown("### 2. Localization & Screening Verdict")
                verdict_output = gr.HTML(
                    value="<div style='color: #64748b;'>Upload an image and run inspection to view screening results.</div>"
                )
                output_overlay = gr.Image(
                    label="Defect Localization Heatmap (Red = Anomalous Region)",
                    type="numpy",
                    height=360,
                )
                score_output = gr.Markdown()
                model_meta_output = gr.HTML()
                disclaimer_output = gr.HTML()

        # Connect button click
        inspect_btn.click(
            fn=predict_quality,
            inputs=[input_image, category_dropdown, threshold_slider],
            outputs=[
                output_overlay,
                verdict_output,
                score_output,
                model_meta_output,
                disclaimer_output,
            ],
        )

        # Preloaded example gallery
        gr.Markdown("### 3. Real Benchmark Verification Examples (MVTec AD)")
        examples = [
            [str(EXAMPLES_DIR / "zipper_good.png"), "zipper", 0.415],
            [str(EXAMPLES_DIR / "zipper_defect.png"), "zipper", 0.415],
            [str(EXAMPLES_DIR / "capsule_good.png"), "capsule", 0.320],
            [str(EXAMPLES_DIR / "capsule_defect.png"), "capsule", 0.320],
        ]

        # Only display examples that exist on disk
        valid_examples = [ex for ex in examples if Path(ex[0]).exists()]
        if valid_examples:
            gr.Examples(
                examples=valid_examples,
                inputs=[input_image, category_dropdown, threshold_slider],
                outputs=[
                    output_overlay,
                    verdict_output,
                    score_output,
                    model_meta_output,
                    disclaimer_output,
                ],
                fn=predict_quality,
                cache_examples=False,
                label="Click any sample to test instantly:",
            )

    return demo


def main() -> None:
    demo = create_demo()
    port = int(os.environ.get("PORT", "7860"))
    print(f"Launching Universal Quality AI Gradio Demo on http://127.0.0.1:{port} ...")
    demo.launch(server_name="127.0.0.1", server_port=port, share=False)


if __name__ == "__main__":
    main()
