"""Database side of C5: datasets, model versions and the real gallery's inspections (replay)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid5

from cportal_core.models import (
    Facility,
    ImageDataset,
    InspectionImage,
    InspectionResult,
    ModelVersion,
    Organization,
)
from cportal_core.names import display_name
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from cportal_c5 import MODEL_VERSION
from cportal_c5.config import load_config
from cportal_c5.gallery import NS, GalleryImage, image_key

DATASET_URL = {
    "DS-VIS-01": "https://www.mvtec.com/company/research/datasets/mvtec-ad",
    "DS-VIS-02": "https://github.com/amazon-science/spot-diff",
    "DS-VIS-04": "https://universe.roboflow.com/fabricdefectdetection-qygi0/stitchnet-defect-detection",
}


def _lineage(source: str, key: str) -> dict[str, Any]:
    return {
        "source_id": source,
        "source_record_id": key[:256],
        "data_mode": "replay",
        "is_synthetic": False,
        "generator_version": MODEL_VERSION,
    }


def model_id(category: str) -> UUID:
    return uuid5(NS, f"model:{category}")


def save_category(
    session: Session,
    category: str,
    report: dict[str, Any],
    method: str,
    gallery: list[GalleryImage],
) -> dict[str, int]:
    """Replace one category's dataset row, model version, gallery images and results."""
    spec = load_config()["categories"][category]
    ds = spec["dataset"]
    dataset_id = uuid5(NS, f"dataset:{category}")
    session.merge(
        ImageDataset(
            id=dataset_id, **_lineage(ds, category), dataset_ref=spec["source"],
            title=spec["source"], licence=spec["licence"], nc=bool(spec["nc"]),
            url=DATASET_URL.get(ds), task="anomaly", categories=[category],
            classes=sorted({g.item.label for g in gallery}), n_images=len(gallery),
            splits=report["split"],
        )
    )  # fmt: skip
    mid = model_id(category)
    m = report["methods"][method]
    session.merge(
        ModelVersion(
            id=mid, **_lineage("c5", f"model:{category}"), capability="c5",
            name=f"c5-{method.replace('_', '-')} ({category})", version=MODEL_VERSION,
            artifact_uri=f"models/c5/{category}.npz",
            card={"path": "docs/model-cards/c5-defect-intel.md", "encoder": "DINOv2-S (ONNX)",
                  "method": method, "threshold": m["threshold"], "data_licence": spec["licence"]},
            metrics=report, licence=f"encoder Apache-2.0; data {spec['licence']}", is_active=True,
        )
    )  # fmt: skip
    session.flush()
    old = select(InspectionImage.id).where(
        InspectionImage.category == category, InspectionImage.is_synthetic.is_(False)
    )
    session.execute(delete(InspectionResult).where(InspectionResult.image_id.in_(old)))
    session.execute(
        delete(InspectionImage).where(
            InspectionImage.category == category, InspectionImage.is_synthetic.is_(False)
        )
    )
    images, results = [], []
    for g in gallery:
        key = image_key(g.item)
        images.append(
            {
                "id": g.id, **_lineage(ds, key), "dataset_id": dataset_id, "category": category,
                "split": "test", "label": g.item.label, "uri": g.uri, "mask_uri": None,
                "width": g.width, "height": g.height, "source_dataset": spec["source"],
            }
        )  # fmt: skip
        results.append(
            {
                "id": uuid5(NS, f"result:{g.id}"), **_lineage("c5", key), "image_id": g.id,
                "model_version_id": mid, "image_score": round(g.score, 6),
                "is_anomalous": g.flagged, "threshold": m["threshold"], "defect_type": None,
                "severity": None, "heatmap_uri": g.heatmap_uri, "mask_uri": None,
                "latency_ms": round(report["encode_ms_per_image"] + m["score_ms"], 1),
            }
        )  # fmt: skip
    session.execute(insert(InspectionImage), images)
    session.execute(insert(InspectionResult), results)
    return {"images": len(images), "results": len(results)}


def line_id(line_key: str) -> UUID:
    return uuid5(NS, f"line:{line_key}")


def save_risk(session: Session, scenario_id: UUID, lots: list[Any]) -> dict[str, int]:
    """P(next lot fails) per line and the pre-inspection risk of every lot (`prediction`)."""
    from cportal_core.models import Prediction

    from cportal_c5 import risk

    session.execute(
        delete(Prediction).where(
            Prediction.capability == "c5", Prediction.scenario_id == scenario_id
        )
    )
    if not lots:
        return {"lines": 0, "lots": 0}
    report = risk.evaluate(lots)
    mid = uuid5(NS, f"model:lot-risk:{scenario_id}")
    lineage = {
        "source_id": "c5",
        "data_mode": "synthetic",
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "generator_version": MODEL_VERSION,
    }
    session.merge(
        ModelVersion(
            id=mid, **lineage, source_record_id="lot-risk", capability="c5",
            name="c5-lot-risk-betabinomial", version=MODEL_VERSION, artifact_uri=None,
            card={"path": "docs/model-cards/c5-defect-intel.md", "method": "beta-binomial EB"},
            metrics=report, licence="code only", is_active=True,
        )
    )  # fmt: skip
    session.flush()
    model = risk.RiskModel(lots)
    spc = risk.spc(lots)
    now = max(lot.produced_at for lot in lots)
    rows: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for lot in lots:
        last[lot.line_key] = lot
        p = model.p_fail(
            lot.line_key, lot.facility_id, lot.industry, lot.produced_at, lot.n, lot.accept
        )
        rows.append(
            _pred(lineage, mid, "batch", lot.id, lot.produced_at, p, {"line": lot.line_key})
        )
    for key, lot in last.items():
        a, b = model.posterior(key, lot.facility_id, lot.industry, now + timedelta(hours=1))
        p = model.p_fail(
            key, lot.facility_id, lot.industry, now + timedelta(hours=1), lot.n, lot.accept
        )
        chart = spc[key]
        rows.append(
            _pred(lineage, mid, "line", line_id(key), now, p, {
                "facility_id": str(lot.facility_id), "line": lot.line, "industry": lot.industry,
                "rate": round(a / (a + b), 5), "next_plan": {"n": lot.n, "accept": lot.accept},
                "alarm_now": chart["alarm_now"], "alarms": chart["alarms"],
            })
        )  # fmt: skip
    session.execute(insert(Prediction), rows)
    return {"lines": len(last), "lots": len(lots)}


def _pred(
    lineage: dict[str, Any],
    mid: UUID,
    kind: str,
    target: UUID,
    at: Any,
    p: float,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": uuid5(NS, f"pred:{kind}:{target}:{lineage['scenario_id']}"),
        **lineage,
        "source_record_id": f"{kind}:{target}",
        "available_at": at,
        "capability": "c5",
        "target_type": kind,
        "target_id": target,
        "as_of": at,
        "horizon_h": None,
        "value": round(p, 4),
        "quantiles": {},
        "dist_params": {},
        "model_version_id": mid,
        "explanation": extra,
        "features_hash": None,
    }


def plant_label(org: Organization, facility: Facility) -> str:
    """Guarded name for quality views (Q-05): never a real firm next to synthetic defects."""
    name = display_name(org.name_key, org.name, adverse=True)
    place = (facility.cluster or "").replace("_", " ").title().replace("Epz", "EPZ")
    return f"{name} – {place} unit" if place else name
