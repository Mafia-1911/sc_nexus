"""/graph (C1), /routes (C3), /shipments (Nexus), /quality (C5), /models, /jobs.

Read shapes are fixed now; analytics, planning and inspection are jobs that arrive with their
capability (M3–M7). Organization names go through the active name pack; views that attach
adverse attributes (quality) ask for the guarded, fictional name (Q-05).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from cportal_core.models import (
    Batch,
    Facility,
    ImageDataset,
    Job,
    ModelVersion,
    Organization,
    Product,
    Shipment,
    ShipmentLeg,
    SupplyEdge,
)
from cportal_core.names import display_name
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from cportal_api.deps import ScopeDep, SessionDep, meta
from cportal_api.jobs import enqueue
from cportal_api.schemas import (
    BatchOut,
    DatasetOut,
    Envelope,
    GraphOut,
    JobAccepted,
    ModelOut,
    ShipmentOut,
)

router = APIRouter()


@router.get("/graph", response_model=Envelope[GraphOut], tags=["graph"])
def supply_graph(
    session: SessionDep,
    scope: ScopeDep,
    industry: Annotated[str | None, Query(description="garments | pharma")] = None,
) -> Envelope[GraphOut]:
    """Facilities (nodes) and supply edges, for Sigma.js. Neutral view: display names apply."""
    rows = session.execute(
        select(Facility, Organization)
        .join(Organization, Organization.id == Facility.organization_id)
        .where(scope.rows(Facility))
    ).all()
    facilities = [(f, o) for f, o in rows if not industry or o.industry in (industry, None)]
    keep = {f.id for f, _ in facilities}
    nodes = [
        {
            "id": str(f.id),
            "facility_type": f.facility_type,
            "cluster": f.cluster,
            "organization": display_name(o.name_key, o.name),
            "org_kind": o.kind,
            "is_fictional": o.is_fictional,
        }
        for f, o in facilities
    ]
    edges_rows = session.execute(
        select(SupplyEdge, Product.sku)
        .join(Product, Product.id == SupplyEdge.product_id)
        .where(scope.rows(SupplyEdge))
    ).all()
    edges = [
        {
            "source": str(e.from_facility_id),
            "target": str(e.to_facility_id),
            "product": sku,
            "share": e.share,
            "lead_time_mean_d": e.lead_time_mean_d,
            "mode": e.mode,
        }
        for e, sku in edges_rows
        if e.from_facility_id in keep and e.to_facility_id in keep
    ]
    return Envelope(
        data=GraphOut(nodes=nodes, edges=edges), meta=meta([f for f, _ in facilities], scope)
    )


@router.get("/graph/analytics", tags=["graph"], responses={501: {"description": "M3"}})
def graph_analytics() -> None:
    raise HTTPException(501, "Dominators, HHI and centralities arrive with C1 (M3).")


@router.post(
    "/graph/what-if",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAccepted,
    tags=["graph"],
)
def graph_what_if(session: SessionDep, body: dict[str, Any]) -> JobAccepted:
    """Queue a C1 cascade what-if (e.g. {"close_port": "BDCGP", "days": 3})."""
    return enqueue(session, "c1.what_if", body)


@router.post(
    "/routes/plan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAccepted,
    tags=["routes"],
)
def plan_route(session: SessionDep, body: dict[str, Any]) -> JobAccepted:
    """Queue a C3 Pareto route request (origin, destination, cargo profile, deadline)."""
    return enqueue(session, "c3.plan", body)


@router.get("/shipments", response_model=Envelope[list[ShipmentOut]], tags=["shipments"])
def list_shipments(
    session: SessionDep,
    scope: ScopeDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[ShipmentOut]]:
    rows = session.scalars(
        select(Shipment).where(scope.rows(Shipment)).order_by(Shipment.planned_eta).limit(limit)
    ).all()
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


@router.get("/quality/batches", response_model=Envelope[list[BatchOut]], tags=["quality"])
def list_batches(
    session: SessionDep,
    scope: ScopeDep,
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[BatchOut]]:
    """Adverse view (defects): organizations show their guarded name (Q-05 guardrail)."""
    q = select(Batch).where(scope.rows(Batch))
    if status_:
        q = q.where(Batch.status == status_)
    rows = session.scalars(q.order_by(Batch.produced_at.desc()).limit(limit)).all()
    names = _facility_names(
        {b.facility_id for b in rows} | {b.supplier_facility_id for b in rows}, session
    )
    out = [
        BatchOut(
            id=b.id,
            lot_code=b.lot_code,
            status=b.status,
            produced_at=b.produced_at,
            size_units=b.size_units,
            aql_result=b.aql_result,
            facility=names.get(b.facility_id, "?"),
            supplier=names.get(b.supplier_facility_id) if b.supplier_facility_id else None,
        )
        for b in rows
    ]
    return Envelope(data=out, meta=meta(rows, scope))


def _facility_names(ids: set[Any], session: SessionDep) -> dict[Any, str]:
    rows = session.execute(
        select(Facility.id, Organization.name_key, Organization.name)
        .join(Organization, Organization.id == Facility.organization_id)
        .where(Facility.id.in_([i for i in ids if i]))
    ).all()
    return {fid: display_name(key, name, adverse=True) for fid, key, name in rows}


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


@router.post(
    "/quality/inspections",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAccepted,
    tags=["quality"],
)
def inspect(session: SessionDep, body: dict[str, Any]) -> JobAccepted:
    """Queue a C5 inspection of images (M7)."""
    return enqueue(session, "c5.inspect", body)


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
