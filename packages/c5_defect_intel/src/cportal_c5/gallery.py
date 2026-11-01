"""Precomputed gallery (C5-AC02: the heavy path is precomputed, the live path is light).

For each evaluated category: a 384 px thumbnail and a transparent heatmap overlay of every test
image (`data/c5/gallery/<category>/`, never committed: MVTec is non-commercial), and the live
few-shot bank with its threshold (`models/c5/<category>.npz`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from cportal_c5.config import ARTIFACTS, MODELS
from cportal_c5.datasets import Item
from cportal_c5.evaluate import MethodResult
from cportal_c5.vision import Encoder, Features

NS = uuid5(NAMESPACE_URL, "cportal/c5")
THUMB = 384
# Perceptual ramp (inferno-like): dark purple → red → yellow; alpha grows with the score.
STOPS = np.array(
    [
        [0.0, 20, 11, 52],
        [0.35, 120, 28, 109],
        [0.6, 212, 72, 66],
        [0.8, 250, 140, 10],
        [1.0, 252, 255, 164],
    ]
)


def image_key(item: Item) -> str:
    """Folder and file: MVTec repeats `000.png` in every defect folder."""
    return f"{item.category}:{item.path.parent.name}/{item.path.name}"


def image_id(item: Item) -> UUID:
    return uuid5(NS, f"image:{image_key(item)}")


@dataclass
class GalleryImage:
    id: UUID
    item: Item
    score: float
    flagged: bool
    width: int
    height: int
    uri: str
    heatmap_uri: str


def overlay(heat: NDArray[np.float32], threshold: float, size: tuple[int, int]) -> Image.Image:
    """RGBA heatmap: transparent below 0.6 × threshold, opaque warm colours above."""
    v = np.clip((heat - 0.6 * threshold) / (1.0 * threshold), 0.0, 1.0)
    rgb = np.stack([np.interp(v, STOPS[:, 0], STOPS[:, c]) for c in (1, 2, 3)], axis=-1)
    alpha = (np.clip(v * 1.4, 0, 1) * 200).astype(np.uint8)
    rgba = np.concatenate([rgb.astype(np.uint8), alpha[..., None]], axis=-1)
    return Image.fromarray(rgba, mode="RGBA").resize(size, Image.Resampling.BILINEAR)


def write(
    category: str, test: list[Item], result: MethodResult, root: Path = ARTIFACTS
) -> list[GalleryImage]:
    out_dir = root / "gallery" / category
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for item in test:
        s = result.scores[str(item.path)]
        iid = image_id(item)
        img = Image.open(item.path).convert("RGB")
        w, h = img.size
        img.thumbnail((THUMB, THUMB))
        img.save(out_dir / f"{iid}.jpg", quality=85)
        overlay(s.heatmap, result.threshold, img.size).save(out_dir / f"{iid}_heat.png")
        out.append(
            GalleryImage(
                iid, item, s.score, s.score > result.threshold, w, h,
                f"gallery/{category}/{iid}.jpg", f"gallery/{category}/{iid}_heat.png",
            )
        )  # fmt: skip
    return out


def save_bank(
    category: str, refs: list[Features], method: str, threshold: float, meta: dict[str, Any]
) -> Path:
    """The live path: k reference patch sets (float16) and the threshold of that method."""
    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / f"{category}.npz"
    bank = np.concatenate([r.patches.reshape(-1, r.patches.shape[-1]) for r in refs])
    np.savez_compressed(path, bank=bank.astype(np.float16))
    (MODELS / f"{category}.json").write_text(
        json.dumps({"method": method, "threshold": threshold, **meta}, indent=1)
    )
    return path


def load_bank(category: str) -> tuple[NDArray[np.float32], dict[str, Any]]:
    data = np.load(MODELS / f"{category}.npz")
    meta: dict[str, Any] = json.loads((MODELS / f"{category}.json").read_text())
    return data["bank"].astype(np.float32), meta


def reference_features(encoder: Encoder, refs: list[Item], tile: int | None) -> list[Features]:
    return [encoder.features(Image.open(i.path), tile=tile) for i in refs]
