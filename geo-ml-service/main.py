"""FastAPI entrypoint for the Earth / GeoIntelligence ML service."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api.routes.indicators import router as indicators_router
from app.api.routes.habitability import router as habitability_router
from app.api.routes.patterns import router as patterns_router
from app.api.routes.prospectivity import router as prospectivity_router
from app.api.routes.preprocessing import router as preprocessing_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.environment import router as environment_router
from app.api.routes.report import router as report_router
from app.indicators.open_meteo import OpenMeteoIndicatorProvider
from app.indicators.usgs_elevation import USGSElevationIndicatorProvider

settings = get_settings()
logging.basicConfig(level=settings.log_level_number, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(settings.service_name)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Register only real provider adapters. They make no network calls at startup.
    from app.api.routes.indicators import register_provider
    for name in ("temperature", "rainfall"):
        try: register_provider(name, OpenMeteoIndicatorProvider(name))
        except ValueError as exc:
            if "already registered" not in str(exc): raise
    try: register_provider("elevation", USGSElevationIndicatorProvider())
    except ValueError as exc:
        if "already registered" not in str(exc): raise
    logger.info("Starting %s v%s (environment=%s)", settings.service_name, settings.service_version, settings.environment)
    yield
    logger.info("Shutting down %s", settings.service_name)

app = FastAPI(title="Earth GeoIntelligence ML Service", version=settings.service_version,
              description="Geospatial data discovery, preprocessing, indicators, and evidence-limited analysis APIs.",
              lifespan=lifespan, docs_url="/docs" if settings.docs_enabled else None,
              redoc_url="/redoc" if settings.docs_enabled else None,
              openapi_url="/openapi.json" if settings.docs_enabled else None)

@app.middleware("http")
async def bounded_request_size(request: Request, call_next):
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            length = int(raw_length)
        except ValueError:
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid Content-Length."})
        limit = 52 * 1024 * 1024 if request.headers.get("content-type", "").lower().startswith("multipart/form-data") else 1 * 1024 * 1024
        if length > limit:
            return JSONResponse(status_code=413, content={"success": False, "message": "Request body exceeds the configured size limit."})
    return await call_next(request)

for router in (indicators_router, habitability_router, patterns_router, prospectivity_router, preprocessing_router, ingestion_router, environment_router, report_router):
    app.include_router(router)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"success": False, "message": "Internal server error."})

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name, "environment": settings.environment}

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level=settings.log_level)
