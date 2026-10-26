"""FastAPI app: `/api/v1` REST, `/ws/live`, `/health` (02 §3, 04 §7).

Run: `uv run uvicorn cportal_api.main:app --reload`.
"""

from __future__ import annotations

import asyncio
import json

from cportal_core import __version__
from cportal_core.db import engine
from cportal_core.names import brand_name, load_pack
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from cportal_api.deps import SessionDep
from cportal_api.live import positions_snapshot
from cportal_api.routers import events, kpis, network, ports, scenarios, sources
from cportal_api.schemas import BrandOut, Problem

PROBLEM = "application/problem+json"


def _problem(status: int, title: str, detail: str | None, request: Request) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, instance=str(request.url.path))
    return JSONResponse(body.model_dump(), status_code=status, media_type=PROBLEM)


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{brand_name()} API",
        version=__version__,
        description=(
            f"Cportal ({brand_name()}) API. Every data response carries `meta` with the data "
            "mode (live, replay, synthetic): synthetic rows are never presented as real."
        ),
        responses={404: {"model": Problem}, 422: {"model": Problem}},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException) -> JSONResponse:
        titles = {404: "Not Found", 501: "Not Implemented", 400: "Bad Request"}
        return _problem(
            exc.status_code, titles.get(exc.status_code, "Error"), str(exc.detail), request
        )

    @app.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return _problem(422, "Unprocessable Entity", detail, request)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        try:
            with engine().connect() as conn:
                conn.execute(text("select 1"))
            db = "ok"
        except Exception as exc:  # report, don't crash the probe
            db = f"down: {type(exc).__name__}"
        return {"status": "ok" if db == "ok" else "degraded", "db": db, "version": __version__}

    api = APIRouter(prefix="/api/v1")

    @api.get("/meta", response_model=BrandOut, tags=["meta"])
    def meta_info() -> BrandOut:
        pack = load_pack()
        return BrandOut(
            brand=brand_name(),
            name_pack=pack.pack,
            banner=pack.banner if pack.has_real_names else None,
            has_real_names=pack.has_real_names,
            version=__version__,
        )

    routers = (sources, scenarios, ports, events, network, kpis)
    for module in routers:
        router = module.router
        api.include_router(router)
    app.include_router(api)

    @app.websocket("/ws/live")
    async def live(ws: WebSocket, session: SessionDep, scenario: str = "baseline") -> None:
        """Vessel positions for one scenario, pushed when the replay clock moves, at most once a
        second (02 §10). Real AIS would arrive the same way; today the worker's replay feeds it."""
        await ws.accept()
        await ws.send_text(json.dumps({"type": "hello", "brand": brand_name()}))
        last_ts: str | None = None
        try:
            while True:
                payload = await asyncio.to_thread(positions_snapshot, scenario, session)
                if payload["ts"] != last_ts:
                    last_ts = payload["ts"]
                    await ws.send_text(json.dumps(payload, default=str))
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app


app = create_app()
