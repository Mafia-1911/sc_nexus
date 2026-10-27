"""C3 public API (02 §6): Pareto route plans for an origin, destination and deadline."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from cportal_c3 import MODEL_VERSION, store
from cportal_c3.network import RoadNet
from cportal_c3.plan import Plan, Planner, Request
from cportal_c3.priors import Priors, load_priors
from cportal_c3.schemas import LegOut, PlanOut, RouteIn, RouteResult

NOTES = [
    "Road speeds and congestion are modelled by road class and hour, not live traffic.",
    "Rail and barge timetables are synthetic, calibrated to 2025 press reports.",
    "Tariffs cite press sources of mixed dates; dwell times are estimates until C4.",
]
_lock = threading.Lock()
_cache: dict[str, Any] = {}


def network(session: Session, priors: Priors | None = None) -> RoadNet:
    """The road graph, rebuilt only when `road_edge` changes (one per process)."""
    stamp = store.network_stamp(session)
    with _lock:
        if _cache.get("stamp") != stamp:
            _cache["net"] = store.load_net(session, priors)
            _cache["stamp"] = stamp
        net: RoadNet = _cache["net"]
        return net


def optimize(session: Session, body: RouteIn, save: bool = True) -> RouteResult:
    priors = load_priors()
    for key in (body.origin, body.dest):
        if key not in priors.places:
            raise KeyError(f"unknown place {key!r}; known: {', '.join(priors.places)}")
    if body.origin == body.dest:
        raise ValueError("origin and destination are the same place")
    net = network(session, priors)
    if net.graph.number_of_nodes() == 0:
        raise LookupError("the road network is empty: run `uv run c3 build-graph`")
    depart = (body.depart or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    req = Request(
        origin=body.origin,
        dest=body.dest,
        depart=depart,
        deadline=body.deadline,
        qty_teu=body.qty_teu,
        reefer=body.cargo_profile == "REEFER_2_8C",
        max_transit_h=body.max_transit_h,
    )
    planner = Planner(net, priors, store.factors(session, priors))
    plans = planner.evaluate(req)[:6]
    sweeps = {p.name: planner.sweep(p, req) for p in plans[:3]}
    result = RouteResult(
        origin=req.origin,
        dest=req.dest,
        depart=req.depart,
        deadline=req.deadline,
        qty_teu=req.qty_teu,
        cargo_profile=body.cargo_profile,
        plans=[_out(p, req, priors, sweeps.get(p.name, [])) for p in plans],
        model_version=MODEL_VERSION,
        notes=[*NOTES, *([note] if (note := priors.ban_note()) else [])],
    )
    if save:
        result.request_id = str(store.save(session, req, plans, sweeps, priors))
    return result


def _out(p: Plan, req: Request, priors: Priors, sweep: list[dict[str, Any]]) -> PlanOut:
    p50, p90 = p.quantile(0.5), p.quantile(0.9)
    return PlanOut(
        name=p.name,
        modes=p.modes,
        km=round(p.km, 1),
        time_p50_h=round(p50, 1),
        time_p90_h=round(p90, 1),
        arrival_p50=req.depart + timedelta(hours=p50),
        arrival_p90=req.depart + timedelta(hours=p90),
        on_time_prob=p.on_time_prob,
        cost_bdt=round(p.cost_bdt),
        cost_usd=round(p.cost_bdt / float(priors["fx_bdt_per_usd"])),
        co2e_kg=round(p.co2e_kg, 1),
        co2e_kg_per_teu=round(p.co2e_kg / req.qty_teu, 1),
        pareto_rank=p.pareto_rank,
        explanation=p.explanation,
        legs=[
            LegOut(
                **{k: v for k, v in leg.summary().items() if k not in ("from", "to")},
                origin=leg.origin,
                dest=leg.dest,
                coords=[
                    [round(x, 5), round(y, 5)]
                    for x, y in leg.coords[:: max(1, len(leg.coords) // 400)]
                ],
            )
            for leg in p.legs
        ],
        departures=sweep,
    )
