"""Core inference engine for Universal Quality AI using Anomalib WinCLIP."""

from __future__ import annotations

import logging
import math
import ssl
import sys
import time

try:
    import certifi

    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

import cv2
import numpy as np
from PIL import Image
import torch
import torchvision.transforms.v2 as transforms

from anomalib.models.image import WinClip

logger = logging.getLogger("cportal_c5.engine")


class QualityInspectionEngine:
    """Manages zero-shot anomaly detection models and localized heatmap generation."""

    def __init__(self, device: str | None = None) -> None:
        """Initialize engine device and model registry.

        Args:
            device: 'cuda', 'cpu', or None for automatic discovery.
        """
        if device is None:
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
            else:
                # Use CPU on macOS/x86_64 for full ViT patch-convolution stability
                self.device = torch.device("cpu")
        else:
            self.device = torch.device(device)

        logger.info("QualityInspectionEngine initialized on device: %s", self.device)

        # Standard CLIP ViT-B/16 input resolution
        self.input_size = (240, 240)
        self.transform = transforms.Compose([
            transforms.ToImage(),
            transforms.ToDtype(torch.float32, scale=True),
            transforms.Resize(self.input_size, antialias=True, interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.Normalize(
                mean=(0.48145466, 0.4578275, 0.40821073),
                std=(0.26862954, 0.26130258, 0.27577711),
            ),
        ])

        # Cache initialized models per category to avoid redundant prompt re-computation
        self._models: dict[str, WinClip] = {}

    def get_model(self, category: str) -> WinClip:
        """Fetch or initialize a cached WinCLIP zero-shot model for a category."""
        category = category.lower().strip()
        if category not in self._models:
            logger.info("Instantiating WinCLIP for category: '%s' (k_shot=0, zero-shot)", category)
            model = WinClip(class_name=category, k_shot=0, scales=(2, 3))
            model.setup(stage="test")
            model.to(self.device)
            model.eval()
            self._models[category] = model
        return self._models[category]

    def inspect(
        self,
        image: Image.Image | np.ndarray,
        category: str,
    ) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Perform zero-shot defect inspection on an input image.

        Args:
            image: PIL Image or RGB numpy array.
            category: Product category name ('zipper', 'capsule', etc.).

        Returns:
            Tuple of:
                - raw_score: float image anomaly metric
                - anomaly_map: 2D numpy array (240x240)
                - overlay_rgb: RGB numpy array of original image + JET heatmap
                - latency_ms: Inference duration in milliseconds
        """
        category = category.lower().strip()
        t0 = time.perf_counter()

        # Convert input to PIL RGB
        if isinstance(image, np.ndarray):
            orig_pil = Image.fromarray(image).convert("RGB")
        elif isinstance(image, Image.Image):
            orig_pil = image.convert("RGB")
        else:
            raise TypeError(f"Unsupported image type: {type(image)}. Expected PIL Image or numpy array.")

        model = self.get_model(category)

        # Preprocess to (1, 3, 240, 240) normalized tensor
        tensor_input = self.transform(orig_pil).unsqueeze(0).to(self.device)

        with torch.no_grad():
            inference_batch = model.model(tensor_input)

        raw_score = float(inference_batch.pred_score[0].detach().cpu().item())
        anomaly_map = inference_batch.anomaly_map[0].detach().cpu().float().numpy()

        if not math.isfinite(raw_score):
            raise ValueError(f"Model returned non-finite anomaly score: {raw_score}")

        # Render visual overlay
        overlay_rgb = self.generate_heatmap_overlay(orig_pil, anomaly_map)
        latency_ms = (time.perf_counter() - t0) * 1000

        return raw_score, anomaly_map, overlay_rgb, latency_ms

    @staticmethod
    def generate_heatmap_overlay(
        orig_img: Image.Image,
        anomaly_map: np.ndarray,
        alpha: float = 0.5,
    ) -> np.ndarray:
        """Render a colorized JET heatmap blended over the original RGB image."""
        orig_np = np.array(orig_img)
        h, w = orig_np.shape[:2]

        h_min, h_max = float(anomaly_map.min()), float(anomaly_map.max())
        if h_max > h_min:
            norm_map = (anomaly_map - h_min) / (h_max - h_min)
        else:
            norm_map = np.zeros_like(anomaly_map)

        heatmap_uint8 = np.uint8(255 * norm_map)
        heatmap_resized = cv2.resize(heatmap_uint8, (w, h), interpolation=cv2.INTER_LINEAR)

        color_map = cv2.applyColorMap(heatmap_resized, cv2.COLORMAP_JET)
        color_map_rgb = cv2.cvtColor(color_map, cv2.COLOR_BGR2RGB)

        blended = cv2.addWeighted(orig_np, alpha, color_map_rgb, 1.0 - alpha, 0)
        return blended
