"""FastAPI: cienka warstwa HTTP nad ``api.service``.

    uv run uvicorn api.main:app --reload --port 8000

Dokumentacja interaktywna: http://localhost:8000/docs. Kontrakt: docs/API_CONTRACT.md + api/openapi.json.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.query import PatchRejected

from . import chat, service
from .schemas import (
    AnalogsRequest,
    AnalogsResponse,
    EarthRegion,
    ErrorCode,
    ErrorResponse,
    Health,
    Meta,
    MoonQuery,
    MoonSite,
    PatchGrid,
)

API_PREFIX = "/api/v1"

COMMON_ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
LOOKUP_ERRORS = {**COMMON_ERRORS, 404: {"model": ErrorResponse}}
PATCH_ERRORS = {**LOOKUP_ERRORS, 503: {"model": ErrorResponse}}

app = FastAPI(
    title="Moon -> Earth terrain analogs API",
    version="1.0.0",
    description=(
        "Kontrakt między backendem a frontendem. Podobieństwo cech terenu (DEM), "
        "a nie przydatność lądowiska - zob. GET /meta -> limitations."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _error(status: int, code: ErrorCode, message: str, details: list[dict] | None = None) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def _invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    details = [{k: v for k, v in d.items() if k != "ctx"} for d in details]
    return _error(422, "INVALID_REQUEST", "Invalid request parameters", details)


@app.exception_handler(service.NotFound)
async def _not_found(_: Request, exc: service.NotFound) -> JSONResponse:
    return _error(404, "NOT_FOUND", str(exc))


@app.exception_handler(PatchRejected)
async def _patch_rejected(_: Request, exc: PatchRejected) -> JSONResponse:
    return _error(422, "PATCH_REJECTED", str(exc))


@app.exception_handler(service.RasterUnavailable)
async def _raster_unavailable(_: Request, exc: service.RasterUnavailable) -> JSONResponse:
    return _error(503, "RASTER_UNAVAILABLE", str(exc))


@app.exception_handler(Exception)
async def _internal(_: Request, exc: Exception) -> JSONResponse:
    return _error(500, "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")


router = APIRouter(prefix=API_PREFIX)


@router.get("/health", response_model=Health, tags=["meta"])
def get_health() -> Health:
    return service.health()


@router.get("/meta", response_model=Meta, tags=["meta"], responses=COMMON_ERRORS)
def get_meta() -> Meta:
    return service.meta()


@router.get("/moon/sites", response_model=list[MoonSite], tags=["moon"], responses=COMMON_ERRORS)
def get_moon_sites() -> list[MoonSite]:
    return service.moon_sites()


@router.get("/moon/patch", response_model=PatchGrid, tags=["moon"], responses=PATCH_ERRORS)
def get_moon_patch(query: Annotated[MoonQuery, Query()]) -> PatchGrid:
    """Siatka wysokości łatki Księżyca: ``?site_id=moon_apollo_11`` albo ``?lat=..&lon=..``."""
    return service.moon_patch(query)


@router.get("/earth/regions", response_model=list[EarthRegion], tags=["earth"], responses=COMMON_ERRORS)
def get_earth_regions() -> list[EarthRegion]:
    return service.earth_regions()


@router.get("/earth/patches/{patch_id}", response_model=PatchGrid, tags=["earth"], responses=LOOKUP_ERRORS)
def get_earth_patch(patch_id: str) -> PatchGrid:
    return service.earth_patch(patch_id)


@router.post("/analogs", response_model=AnalogsResponse, tags=["analogs"], responses=PATCH_ERRORS)
def post_analogs(req: AnalogsRequest) -> AnalogsResponse:
    """Ranking najbardziej podobnych łatek Ziemi dla miejsca na Księżycu."""
    return service.analogs(req)


app.include_router(router)
app.include_router(chat.router, prefix=API_PREFIX)
