"""Health endpoint router for the Earth GeoIntelligence ML service."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["system"])
settings = get_settings()


class HealthResponse(BaseModel):
    """Liveness response describing the running service configuration."""

    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Check service health")
async def health() -> HealthResponse:
    """Return liveness and non-sensitive service metadata."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
    )

