"""/routes (C3 §8): Pareto route plans with P50/P90, on-time probability, cost and CO2e.

Planning runs in the request (C3-AC02: < 5 s on CPU); the road graph is cached per process and
reloaded only when `road_edge` changes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cportal_c3 import MODEL_VERSION, service
from cportal_c3.priors import load_priors
from cportal_c3.schemas import RouteIn, RouteResult
from cportal_core.models import RouteOption, RouteRequest
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from cportal_api.deps import SessionDep, meta
from cportal_api.schemas import Envelope, Meta

router = APIRouter(tags=["routes"])


def _meta(rows: list[Any]) -> Meta:
    m = meta(rows, None, model_version=MODEL_VERSION, note="; ".join(service.NOTES))
    m.sources = ["DS-GEO-01", "DS-GEO-05", "c3"]
    return m


@router.get("/routes/places", response_model=Envelope[list[dict[str, Any]]])
def places() -> Envelope[list[dict[str, Any]]]:
    """Origins and destinations the planner knows (ports, ICDs, industrial clusters)."""
    data = [{"key": k, **v} for k, v in load_priors().places.items()]
    return Envelope(data=data, meta=meta([], None, note="config/priors/c3.yaml"))


@router.get("/network/services", response_model=Envelope[list[dict[str, Any]]])
def services(mode: str | None = None) -> Envelope[list[dict[str, Any]]]:
    """Rail and barge services (synthetic timetables calibrated to 2025 press facts)."""
    data = [
        {"key": k, **v}
        for k, v in load_priors()["services"].items()
        if mode is None or v["mode"] == mode
    ]
    return Envelope(data=data, meta=meta([], None, note="synthetic timetables (C3 §11)"))


@router.post("/routes/optimize", response_model=Envelope[RouteResult])
def optimize(body: RouteIn, session: SessionDep) -> Envelope[RouteResult]:
    try:
        result = service.optimize(session, body)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    session.commit()
    rows = session.scalars(
        select(RouteOption).where(RouteOption.request_id == UUID(str(result.request_id)))
    ).all()
    return Envelope(data=result, meta=_meta(list(rows)))


@router.get("/routes/{request_id}", response_model=Envelope[dict[str, Any]])
def get_route(request_id: UUID, session: SessionDep) -> Envelope[dict[str, Any]]:
    request = session.get(RouteRequest, request_id)
    if request is None:
        raise HTTPException(404, "route request not found")
    options = session.scalars(
        select(RouteOption)
        .where(RouteOption.request_id == request_id)
        .order_by(RouteOption.pareto_rank, RouteOption.time_p50_h)
    ).all()
    return Envelope(
        data={
            "request_id": str(request.id),
            "constraints": request.constraints,
            "deadline": request.deadline,
            "options": [
                {
                    "legs": o.legs,
                    "time_p50_h": o.time_p50_h,
                    "time_p90_h": o.time_p90_h,
                    "cost_bdt": o.cost_bdt,
                    "co2e_kg": o.co2e_kg,
                    "on_time_prob": o.on_time_prob,
                    "pareto_rank": o.pareto_rank,
                    "explanation": o.explanation,
                }
                for o in options
            ],
        },
        meta=_meta(list(options)),
    )
