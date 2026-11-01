"""/quality (C5 §8): the lot board with AQL, lot detail with inspected items and options, lines
with risk and SPC, the real image gallery, and live inspection of one uploaded image.

Lots, lines and options are synthetic (fictional plants, real dataset images); the gallery is
real dataset images with their licences. Image files come only from `data/c5/`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from cportal_c5 import MODEL_VERSION, service
from cportal_c5.config import ARTIFACTS
from cportal_c5.schemas import ItemOut, LineOut, LiveResultOut, LotDetailOut, LotOut, SpcOut
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from cportal_api.deps import ScopeDep, SessionDep
from cportal_api.schemas import Envelope, Meta

router = APIRouter(tags=["quality"])
NOTE = (
    "Lots, lines and plants are synthetic; every inspected item is a real dataset image (MVTec AD "
    "CC BY-NC-SA, StitchNet CC BY) mapped to a fictional SKU. Pharma lots are never released "
    "automatically."
)


def _meta(mode: Literal["synthetic", "replay"], scope: Any = None, n: int = 1) -> Meta:
    return Meta(
        mode=mode if n else "none",
        modes={mode: n} if n else {},
        sources=["sim", "c5", "DS-VIS-01", "DS-VIS-04"]
        if mode == "synthetic"
        else ["DS-VIS-01", "DS-VIS-04"],
        as_of=datetime.now(UTC),
        scenario=scope.key if scope else None,
        model_version=MODEL_VERSION,
        note=NOTE,
    )


@router.get("/quality/summary", response_model=Envelope[dict[str, Any]])
def summary(session: SessionDep, scope: ScopeDep) -> Envelope[dict[str, Any]]:
    """KPIs for the Quality Lab: lots, rejections, QA holds, orders at risk, lines alarming."""
    data = service.summary(session, scope.scenario_id)
    return Envelope(data=data, meta=_meta("synthetic", scope, data["lots"]))


@router.get("/quality/batches", response_model=Envelope[list[LotOut]])
def batches(
    session: SessionDep,
    scope: ScopeDep,
    status: Annotated[str | None, Query(description="released | rejected | quarantine")] = None,
    industry: Annotated[str | None, Query(description="garments | pharma")] = None,
) -> Envelope[list[LotOut]]:
    rows = service.lots(session, scope.scenario_id, status, industry)
    return Envelope(data=rows, meta=_meta("synthetic", scope, len(rows)))


@router.get("/quality/batches/{batch_id}", response_model=Envelope[LotDetailOut])
def batch(batch_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[LotDetailOut]:
    """AQL result, the inspected items with heatmaps, the order, the alert and its options."""
    out = service.lot(session, scope.scenario_id, batch_id)
    if out is None:
        raise HTTPException(404, "unknown lot in this scenario")
    return Envelope(data=out, meta=_meta("synthetic", scope))


@router.get("/quality/lines", response_model=Envelope[list[LineOut]])
def lines(session: SessionDep, scope: ScopeDep) -> Envelope[list[LineOut]]:
    """Every production line: P(next lot fails AQL), its defect rate and SPC alarm state."""
    rows = service.lines(session, scope.scenario_id)
    return Envelope(data=rows, meta=_meta("synthetic", scope, len(rows)))


@router.get("/quality/lines/{line_id}/spc", response_model=Envelope[SpcOut])
def line_spc(line_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[SpcOut]:
    out = service.spc(session, scope.scenario_id, line_id)
    if out is None:
        raise HTTPException(404, "unknown line in this scenario")
    return Envelope(data=out, meta=_meta("synthetic", scope))


@router.get("/quality/gallery", response_model=Envelope[list[ItemOut]])
def gallery(
    session: SessionDep,
    category: Annotated[
        str | None, Query(description="stitch | pill | capsule | carpet | leather")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 48,
) -> Envelope[list[ItemOut]]:
    """Real dataset test images with the model's score, flag and heatmap (precomputed)."""
    rows = service.gallery(session, category, limit)
    return Envelope(data=rows, meta=_meta("replay", None, len(rows)))


@router.post("/quality/inspections", response_model=Envelope[LiveResultOut])
async def inspect(
    image: Annotated[UploadFile, File(description="JPEG or PNG, ≤ 10 MB")],
    category: Annotated[str, Form(description="few-shot bank: stitch, pill, capsule, …")],
) -> Envelope[LiveResultOut]:
    """Score one image against the category's few-shot bank (CPU, ≈ 0.4 s): score, flag,
    heatmap. Assistive only: a person confirms."""
    data = await image.read()
    try:
        out = await run_in_threadpool(service.Live.inspect, data, category)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Envelope(data=out, meta=_meta("replay", None))


@router.get("/quality/files/{path:path}", include_in_schema=False)
def files(path: str) -> FileResponse:
    """Gallery thumbnails, heatmaps and uploads from `data/c5/` (nothing else)."""
    root = ARTIFACTS.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root) + "/") or target.suffix not in (".jpg", ".png"):
        raise HTTPException(404, "not found")
    if not target.is_file() or not path.startswith(("gallery/", "uploads/")):
        raise HTTPException(404, "not found")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=86400"})
