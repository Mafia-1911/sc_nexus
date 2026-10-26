"""/scenarios: seeded worlds and their results (Scenario Studio runs are jobs, M8)."""

from __future__ import annotations

from cportal_core.models import Scenario, ScenarioResult
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from cportal_api.deps import SessionDep, meta
from cportal_api.jobs import enqueue
from cportal_api.schemas import Envelope, JobAccepted, ScenarioOut, ScenarioResultOut

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=Envelope[list[ScenarioOut]])
def list_scenarios(session: SessionDep) -> Envelope[list[ScenarioOut]]:
    rows = session.scalars(select(Scenario).order_by(Scenario.is_baseline.desc(), Scenario.key))
    out = [
        ScenarioOut(
            key=r.key, name=r.name, is_baseline=r.is_baseline, seed=r.seed, definition=r.definition
        )
        for r in rows
    ]
    return Envelope(data=out, meta=meta(note="synthetic scenarios"))


@router.get("/{key}/results", response_model=Envelope[list[ScenarioResultOut]])
def scenario_results(key: str, session: SessionDep) -> Envelope[list[ScenarioResultOut]]:
    scenario = session.scalar(select(Scenario).where(Scenario.key == key))
    if scenario is None:
        raise HTTPException(404, f"unknown scenario {key!r}")
    rows = session.scalars(
        select(ScenarioResult).where(ScenarioResult.run_scenario_id == scenario.id)
    ).all()
    out = [
        ScenarioResultOut(capability=r.capability, kpis=r.kpis, artifacts=r.artifacts) for r in rows
    ]
    return Envelope(data=out, meta=meta(rows))


@router.post("/{key}/runs", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def run_scenario(key: str, session: SessionDep) -> JobAccepted:
    """Queue a scenario run (the worker executes it from M2; M8 adds the full engine)."""
    if session.scalar(select(Scenario.id).where(Scenario.key == key)) is None:
        raise HTTPException(404, f"unknown scenario {key!r}")
    return enqueue(session, "scenario.run", {"scenario": key})
