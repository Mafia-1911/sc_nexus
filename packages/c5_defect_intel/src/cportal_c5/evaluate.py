"""Evaluate zero- and few-shot anomaly detection per category (C5-AC01, AC02, AC03).

Image AUROC on the test images; pixel AUROC where masks exist (MVTec); the threshold at the
target FPR from held-out normal images, with recall and the realised FPR on the test images;
encode and score latency per image. Methods: MuSc-style zero-shot over the unlabelled lot
(test + calibration images) and AnomalyDINO few-shot at each k.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from sklearn.metrics import roc_auc_score

from cportal_c5.config import load_config
from cportal_c5.datasets import Item, load
from cportal_c5.vision import Encoder, Features, FewShot, Scored, mutual_scores

MAX_PIXELS = 3_000_000


@dataclass
class MethodResult:
    name: str
    scores: dict[str, Scored]  # by image path
    threshold: float
    metrics: dict[str, Any] = field(default_factory=dict)


def _pixel_auroc(test: list[Item], scores: dict[str, Scored], seed: int = 0) -> float | None:
    if not any(i.mask for i in test):
        return None
    ys, ss = [], []
    for item in test:
        heat = scores[str(item.path)].heatmap
        if item.mask is not None:
            mask = (
                Image.open(item.mask)
                .convert("L")
                .resize(heat.shape[::-1], Image.Resampling.NEAREST)
            )
            truth = np.asarray(mask) > 127
        else:
            truth = np.zeros(heat.shape, dtype=bool)
        ys.append(truth.ravel())
        ss.append(heat.ravel())
    y, s = np.concatenate(ys), np.concatenate(ss)
    if len(y) > MAX_PIXELS:
        idx = np.random.default_rng(seed).choice(len(y), MAX_PIXELS, replace=False)
        y, s = y[idx], s[idx]
    return round(float(roc_auc_score(y, s)), 4)


def _metrics(
    test: list[Item], calib: list[Item], scores: dict[str, Scored], fpr: float
) -> tuple[float, dict[str, Any]]:
    y = np.array([i.anomalous for i in test])
    s = np.array([scores[str(i.path)].score for i in test])
    threshold = float(np.quantile([scores[str(i.path)].score for i in calib], 1 - fpr))
    flagged = s > threshold
    by_type = {}
    for kind in sorted({i.label for i in test if i.anomalous}):
        m = np.array([i.label == kind for i in test])
        by_type[kind] = round(float(flagged[m].mean()), 3)
    return threshold, {
        "image_auroc": round(float(roc_auc_score(y, s)), 4),
        "pixel_auroc": _pixel_auroc(test, scores),
        "threshold": round(threshold, 5),
        "recall_at_fpr": round(float(flagged[y].mean()), 3),
        "fpr_on_test_normals": round(float(flagged[~y].mean()), 3),
        "recall_by_type": by_type,
        "score_ms": round(float(np.mean([scores[str(i.path)].latency_ms for i in test])), 1),
        "n_test": len(test),
        "n_anomalous": int(y.sum()),
    }


def evaluate(
    category: str, encoder: Encoder
) -> tuple[dict[str, Any], dict[str, MethodResult], dict[str, Features], list[Item]]:
    cfg = load_config()
    vcfg, tile = cfg["vision"], cfg["categories"][category].get("tile")
    items = load(category)
    refs = [i for i in items if i.split == "ref"]
    calib = [i for i in items if i.split == "calib"]
    test = [i for i in items if i.split == "test"]
    t0 = time.perf_counter()
    feats: dict[str, Features] = {
        str(i.path): encoder.features(Image.open(i.path), tile=tile) for i in items
    }
    encode_ms = (time.perf_counter() - t0) * 1000 / len(items)
    fpr = float(vcfg["target_fpr"])
    results: dict[str, MethodResult] = {}
    lot = calib + test
    zs = mutual_scores([feats[str(i.path)] for i in lot], refs=int(vcfg["musc_refs"]))
    scored = {str(i.path): s for i, s in zip(lot, zs, strict=True)}
    results["zero_shot_musc"] = MethodResult("zero_shot_musc", scored, 0.0)
    for k in vcfg["shots"]:
        model = FewShot([feats[str(i.path)] for i in refs[:k]])
        scored = {str(i.path): model.score(feats[str(i.path)]) for i in lot}
        results[f"few_shot_k{k}"] = MethodResult(f"few_shot_k{k}", scored, 0.0)
    for r in results.values():
        r.threshold, r.metrics = _metrics(test, calib, r.scores, fpr)
    report = {
        "category": category,
        "source": cfg["categories"][category]["source"],
        "licence": cfg["categories"][category]["licence"],
        "split": {"refs": len(refs), "calibration_normals": len(calib), "test": len(test)},
        "tile": tile,
        "encode_ms_per_image": round(encode_ms, 1),
        "methods": {name: r.metrics for name, r in results.items()},
    }
    return report, results, feats, items


def deploy_method(report: dict[str, Any]) -> str:
    """The method the app uses: the best image AUROC of zero-shot and few-shot at the largest k."""
    shots = max(int(k) for k in load_config()["vision"]["shots"])
    pick = ["zero_shot_musc", f"few_shot_k{shots}"]
    return max(pick, key=lambda m: report["methods"][m]["image_auroc"])


def scores_array(result: MethodResult, items: list[Item]) -> NDArray[np.float64]:
    return np.array([result.scores[str(i.path)].score for i in items])
