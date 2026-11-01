"""/routes (C3), /shipments (Nexus), /quality/datasets (C5; the rest is in `quality.py`),
/models, /jobs. (/graph is C1's router.)

Read shapes are fixed now; planning and inspection are jobs that arrive with their capability
(M5–M7). Organization names go through the active name pack; views that attach adverse
attributes (quality) ask for the guarded, fictional name (Q-05).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from cportal_core.enums import ShipmentStatus
from cportal_core.models import (
    ImageDataset,
    Job,
    ModelVersion,
    Shipment,
    ShipmentLeg,
)
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.schemas import (
    DatasetOut,
    Envelope,
    ModelOut,
    ShipmentOut,
)

router = APIRouter()


@router.get("/shipments", response_model=Envelope[list[ShipmentOut]], tags=["shipments"])
def list_shipments(
    session: SessionDep,
    scope: ScopeDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    active: Annotated[
        bool, Query(description="Only shipments not yet delivered or cancelled")
    ] = False,
) -> Envelope[list[ShipmentOut]]:
    q = select(Shipment).where(scope.rows(Shipment))
    if active:
        q = q.where(Shipment.status.not_in([ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED]))
    rows = session.scalars(q.order_by(Shipment.planned_eta).limit(limit)).all()
    return Envelope(data=[_shipment(s) for s in rows], meta=meta(rows, scope))


@router.get("/shipments/{shipment_id}", response_model=Envelope[ShipmentOut], tags=["shipments"])
def get_shipment(shipment_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[ShipmentOut]:
    row = session.scalar(select(Shipment).where(Shipment.id == shipment_id, scope.rows(Shipment)))
    if row is None:
        raise HTTPException(404, "shipment not found")
    legs = session.scalars(
        select(ShipmentLeg).where(ShipmentLeg.shipment_id == row.id).order_by(ShipmentLeg.seq)
    ).all()
    out = _shipment(row)
    out.legs = [
        {
            "seq": leg.seq,
            "mode": leg.mode,
            "from_location_id": str(leg.from_location_id),
            "to_location_id": str(leg.to_location_id),
            "vessel_id": str(leg.vessel_id) if leg.vessel_id else None,
            "planned_dep": leg.planned_dep,
            "planned_arr": leg.planned_arr,
            "actual_dep": leg.actual_dep,
            "actual_arr": leg.actual_arr,
        }
        for leg in legs
    ]
    return Envelope(data=out, meta=meta([row], scope))


def _shipment(s: Shipment) -> ShipmentOut:
    return ShipmentOut(
        id=s.id,
        reference=s.reference,
        status=s.status,
        mode_chain=s.mode_chain,
        cargo_profile=s.cargo_profile,
        planned_eta=s.planned_eta,
        predicted_eta_p50=s.predicted_eta_p50,
        predicted_eta_p90=s.predicted_eta_p90,
    )


@router.get("/quality/datasets", response_model=Envelope[list[DatasetOut]], tags=["quality"])
def list_datasets(session: SessionDep) -> Envelope[list[DatasetOut]]:
    rows = session.scalars(select(ImageDataset).order_by(ImageDataset.dataset_ref)).all()
    out = [
        DatasetOut(
            dataset_ref=d.dataset_ref, title=d.title, licence=d.licence, nc=d.nc, task=d.task,
            n_images=d.n_images, classes=d.classes,
        )
        for d in rows
    ]  # fmt: skip
    return Envelope(data=out, meta=meta(rows))


@router.get("/models", response_model=Envelope[list[ModelOut]], tags=["models"])
def list_models(session: SessionDep) -> Envelope[list[ModelOut]]:
    rows = session.scalars(select(ModelVersion).order_by(ModelVersion.capability)).all()
    out = [
        ModelOut(
            capability=m.capability, name=m.name, version=m.version, is_active=m.is_active,
            licence=m.licence, metrics=m.metrics,
        )
        for m in rows
    ]  # fmt: skip
    return Envelope(data=out, meta=meta(rows, note="model registry; baselines register from M3"))


@router.get("/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: UUID, session: SessionDep) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {
        "job_id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }
