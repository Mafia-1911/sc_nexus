"""Recalibrate C5 thresholds from stored scores, without re-scoring (A-124).

The thresholds were set at 5 % FPR on 30 *training* normals, but MVTec's test normals score
higher, so test false alarms ran at 9-25 %. Here each category's test normals are split in two
by a stable hash of the image id: the threshold is the 95th percentile of one half, and the
false-alarm rate and recall are reported on the other half (defect images are never used to
set it). The new threshold goes into the stored results, the model_version card and the live
bank's metadata (`models/c5/<category>.json`).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import numpy as np
from cportal_core.models import InspectionImage, InspectionResult, ModelVersion
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cportal_c5.gallery import MODELS
from cportal_c5.store import model_id


def _half(image_id: UUID) -> int:
    return image_id.int % 2  # stable: the same images calibrate on every run


def plan(rows: list[tuple[UUID, float, bool]], target_fpr: float = 0.05) -> dict[str, Any]:
    """rows: (image id, score, is_normal). Threshold from one half of the normals, metrics on
    the other half and on every defect image."""
    calib = np.array([s for i, s, normal in rows if normal and _half(i) == 0])
    held = np.array([s for i, s, normal in rows if normal and _half(i) == 1])
    defects = np.array([s for _, s, normal in rows if not normal])
    threshold = float(np.quantile(calib, 1 - target_fpr, method="higher"))
    return {
        "threshold": round(threshold, 6),
        "calibration_normals": len(calib),
        "held_out_normals": len(held),
        "held_out_fpr": round(float(np.mean(held > threshold)), 3) if len(held) else None,
        "recall": round(float(np.mean(defects > threshold)), 3) if len(defects) else None,
        "defects": len(defects),
    }


def recalibrate(session: Session, target_fpr: float = 0.05, apply: bool = True) -> dict[str, Any]:
    rows = session.execute(
        select(InspectionImage.category, InspectionImage.id, InspectionResult.id,
               InspectionResult.image_score, InspectionResult.threshold, InspectionImage.label)
        .join(InspectionResult, InspectionResult.image_id == InspectionImage.id)
        .where(InspectionImage.is_synthetic.is_(False), InspectionImage.split == "test")
    ).all()  # fmt: skip
    out: dict[str, Any] = {}
    for category in sorted({r[0] for r in rows}):
        mine = [r for r in rows if r[0] == category]
        old = float(mine[0][4])
        before = plan([(r[1], r[3], r[5] == "good") for r in mine], target_fpr)
        new = before["threshold"]
        # The same held-out view of the old threshold, for a fair before/after.
        held = [r[3] for r in mine if r[5] == "good" and _half(r[1]) == 1]
        bad = [r[3] for r in mine if r[5] != "good"]
        out[category] = {
            "old": {"threshold": round(old, 6),
                    "held_out_fpr": round(float(np.mean(np.array(held) > old)), 3),
                    "recall": round(float(np.mean(np.array(bad) > old)), 3)},
            "new": before,
        }  # fmt: skip
        if not apply:
            continue
        ids = [r[2] for r in mine]
        session.execute(
            update(InspectionResult)
            .where(InspectionResult.id.in_(ids))
            .values(threshold=new, is_anomalous=InspectionResult.image_score > new)
        )
        mv = session.get(ModelVersion, model_id(category))
        if mv is not None:
            mv.card = {**mv.card, "threshold": new, "calibration": "held-out test normals (A-124)"}
            mv.metrics = {**mv.metrics, "recalibrated": out[category]}
        meta_path = MODELS / f"{category}.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta.update(threshold=new, threshold_before=old, calibration="A-124")
            meta_path.write_text(json.dumps(meta, indent=1))
    return out
