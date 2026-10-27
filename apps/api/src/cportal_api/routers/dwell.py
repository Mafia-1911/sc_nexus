"""C4 port dwell (C4 §8): queue forecast, vessels in port with predictions, one vessel's track.

Predictions are precomputed replays of real GFW calls (`uv run c4 train`); these routes only read.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from cportal_c4 import MODEL_VERSION, service
from cportal_c4.schemas import QueueForecastOut, VesselInPortOut, VesselTrackOut
from fastapi import APIRouter, HTTPException, Query

from cportal_api.deps import SessionDep, meta
from cportal_api.schemas import Envelope, Meta

router = APIRouter(tags=["ports"])
AsOf = Annotated[datetime | None, Query(description="Replay snapshot (default: the latest)")]


def _meta(at: datetime | None, has_rows: bool) -> Meta:
    m = meta([], None, model_version=MODEL_VERSION, note=service.NOTE, as_of=at)
    if has_rows:
        m.mode, m.modes, m.sources = "replay", {"replay": 1}, ["DS-AIS-02", "c4"]
    return m


@router.get("/ports/{locode}/forecast", response_model=Envelope[QueueForecastOut])
def port_forecast(
    locode: str,
    session: SessionDep,
    as_of: AsOf = None,
    horizon_d: Annotated[int, Query(ge=1, le=14)] = 14,
) -> Envelope[QueueForecastOut]:
    """Vessels in the outer anchorage: 60 days of history and a P10/P50/P90 fan (C4-R02)."""
    out = service.forecast(session, locode.upper(), as_of)
    if out is None:
        raise HTTPException(404, f"no C4 predictions for {locode}: run `uv run c4 train {locode}`")
    out.forecast = out.forecast[:horizon_d]
    return Envelope(data=out, meta=_meta(out.as_of, bool(out.history)))


@router.get("/ports/{locode}/predictions", response_model=Envelope[list[VesselInPortOut]])
def port_predictions(
    locode: str, session: SessionDep, as_of: AsOf = None
) -> Envelope[list[VesselInPortOut]]:
    """Vessels in port at the snapshot: departure P10/P50/P90, drivers, and what happened."""
    at, rows = service.vessels(session, locode.upper(), as_of)
    return Envelope(data=rows, meta=_meta(at, bool(rows)))


@router.get("/vessels/{vessel_id}/prediction", response_model=Envelope[VesselTrackOut])
def vessel_prediction(
    vessel_id: UUID, session: SessionDep, as_of: AsOf = None
) -> Envelope[VesselTrackOut]:
    """The vessel's predicted call, with its departure estimate at every snapshot (C4-R03)."""
    out = service.track(session, vessel_id, as_of)
    if out is None:
        raise HTTPException(404, "no C4 prediction for this vessel")
    return Envelope(data=out, meta=_meta(out.updates[-1]["as_of"], True))
