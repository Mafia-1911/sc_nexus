"""Anomaly scoring on DINOv2-S patch features (ONNX, CPU): zero-shot and few-shot (C5 §5).

- **Encoder:** `facebook/dinov2-small` (Apache-2.0) as ONNX (onnx-community export), 14 px
  patches; a 448 px input gives a 32 × 32 grid of 384-d features, L2-normalised.
- **Z0 zero-shot, MuSc-style (ICLR'24) mutual scoring:** within a lot of unlabelled images of
  one category, a patch's score is the mean of its lowest 30 % nearest-patch distances to the
  other images (anomalies are rare, so most other images vouch for normal patches). Our variant:
  DINOv2-S backbone, one layer, up to `refs` other images per image, no RsCIN re-scoring.
- **F1 few-shot, AnomalyDINO (WACV'25):** a patch's score is its cosine distance to the nearest
  patch of k normal reference images.
- **Tiling** for textures and fabric: overlapping tiles, each scored, the map stitched by max.

Image score = mean of the top 1 % patch scores; the heatmap is the patch map, upsampled.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from cportal_c5.config import MODELS

MODEL_URL = "https://huggingface.co/onnx-community/dinov2-small/resolve/main/onnx/model.onnx"
MODEL_PATH = MODELS / "dinov2-small.onnx"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PATCH = 14
F32 = NDArray[np.float32]


def fetch_model(path: Path = MODEL_PATH) -> Path:
    """Download the ONNX encoder once (≈ 88 MB); later runs use the file on disk."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
    tmp.rename(path)
    return path


@dataclass
class Features:
    patches: F32  # (tiles, h*w, d), L2-normalised
    grid: tuple[int, int]
    boxes: list[tuple[int, int, int, int]]  # tile boxes in source pixels (x0, y0, x1, y1)
    size: tuple[int, int]  # source (width, height)


class Encoder:
    def __init__(self, path: Path = MODEL_PATH, side: int = 448, threads: int = 4) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            str(fetch_model(path)), opts, providers=["CPUExecutionProvider"]
        )
        self.input = self.session.get_inputs()[0].name
        self.side = side - side % PATCH

    def _embed(self, img: Image.Image) -> F32:
        x = np.asarray(img.convert("RGB").resize((self.side, self.side), Image.Resampling.BICUBIC))
        x = ((x.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)[None]
        out = self.session.run(None, {self.input: x})[0][0, 1:]  # drop the CLS token
        out = out / np.linalg.norm(out, axis=1, keepdims=True)
        return out.astype(np.float32)

    def features(self, img: Image.Image, tile: int | None = None, overlap: int = 64) -> Features:
        w, h = img.size
        boxes = [(0, 0, w, h)]
        if tile and min(w, h) > tile:
            step = tile - overlap
            xs = sorted({*range(0, w - tile + 1, step), w - tile})
            ys = sorted({*range(0, h - tile + 1, step), h - tile})
            boxes = [(x, y, x + tile, y + tile) for y in ys for x in xs]
        patches = np.stack([self._embed(img.crop(b)) for b in boxes])
        g = self.side // PATCH
        return Features(patches, (g, g), boxes, (w, h))


def _nearest_distance(q: F32, bank: F32, chunk: int = 4096) -> F32:
    """Cosine distance from each query patch to its nearest patch in the bank."""
    best = np.full(len(q), -1.0, dtype=np.float32)
    for start in range(0, len(bank), chunk):
        sims = q @ bank[start : start + chunk].T
        best = np.maximum(best, sims.max(axis=1))
    return np.asarray(1.0 - best, dtype=np.float32)


def image_score(patch_scores: F32) -> float:
    k = max(1, round(patch_scores.size * 0.01))
    return float(np.sort(patch_scores.ravel())[-k:].mean())


@dataclass
class Scored:
    score: float
    heatmap: F32  # source-resolution map (height, width), max-stitched over tiles
    latency_ms: float


def _stitch(f: Features, maps: list[F32], scale: int = 4) -> F32:
    """Paste per-tile patch maps into a source-sized (downscaled by `scale`) map by max."""
    w, h = f.size
    out = np.zeros((h // scale + 1, w // scale + 1), dtype=np.float32)
    for (x0, y0, x1, y1), m in zip(f.boxes, maps, strict=True):
        tw, th = (x1 - x0) // scale, (y1 - y0) // scale
        img = Image.fromarray(m.reshape(f.grid).astype(np.float32), mode="F").resize(
            (tw, th), Image.Resampling.BILINEAR
        )
        region = out[y0 // scale : y0 // scale + th, x0 // scale : x0 // scale + tw]
        np.maximum(region, np.asarray(img)[: region.shape[0], : region.shape[1]], out=region)
    return out


class FewShot:
    """AnomalyDINO: nearest-neighbour distance to the patches of k normal references."""

    def __init__(self, refs: list[Features]) -> None:
        self.bank = np.concatenate([r.patches.reshape(-1, r.patches.shape[-1]) for r in refs])

    def score(self, f: Features) -> Scored:
        t0 = time.perf_counter()
        maps = [_nearest_distance(tile, self.bank) for tile in f.patches]
        heat = _stitch(f, maps)
        return Scored(image_score(np.concatenate(maps)), heat, (time.perf_counter() - t0) * 1000)


def mutual_scores(
    lot: list[Features], refs: int = 32, keep: float = 0.3, seed: int = 0
) -> list[Scored]:
    """MuSc-style zero-shot scoring of a lot of unlabelled images of one category."""
    rng = np.random.default_rng(seed)
    flat = [f.patches.reshape(-1, f.patches.shape[-1]) for f in lot]
    out = []
    for i, f in enumerate(lot):
        t0 = time.perf_counter()
        others = [j for j in range(len(lot)) if j != i]
        if len(others) > refs:
            others = list(rng.choice(others, refs, replace=False))
        maps = []
        for tile in f.patches:
            dists = np.stack([_nearest_distance(tile, flat[j]) for j in others])  # (refs, patches)
            k = max(1, round(len(others) * keep))
            maps.append(np.sort(dists, axis=0)[:k].mean(axis=0).astype(np.float32))
        heat = _stitch(f, maps)
        out.append(
            Scored(image_score(np.concatenate(maps)), heat, (time.perf_counter() - t0) * 1000)
        )
    return out
