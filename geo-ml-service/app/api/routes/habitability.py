"""Evidence-gated habitability screening API built on existing factor modules."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.region import GeographicRegion
from app.habitability.risk_factor import RiskInput
from app.habitability.scoring import HabitabilityInputs, assess_habitability
from app.habitability.temperature_factor import TemperatureInput
from app.habitability.terrain_factor import TerrainInput
from app.habitability.water_factor import WaterInput

router = APIRouter(prefix="/habitability", tags=["habitability"])

class TemperatureValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mean_c: float | None = None
    min_c: float | None = None
    max_c: float | None = None

class WaterValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability_index: float | None = Field(default=None, ge=0, le=1)
    groundwater_depth_m: float | None = Field(default=None, ge=0, le=10000)
    distance_to_surface_water_km: float | None = Field(default=None, ge=0, le=20000)

class TerrainValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    slope_deg: float | None = Field(default=None, ge=0, le=90)

class RiskValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flood: float | None = Field(default=None, ge=0, le=1)
    drought: float | None = Field(default=None, ge=0, le=1)
    wildfire: float | None = Field(default=None, ge=0, le=1)
    seismic: float | None = Field(default=None, ge=0, le=1)

class HabitabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: GeographicRegion
    temperature: TemperatureValues | None = None
    water: WaterValues | None = None
    terrain: TerrainValues | None = None
    risk: RiskValues | None = None
    evidence_sources: list[str] = Field(default_factory=list, max_length=20)

    @staticmethod
    def _trim(values: list[str]) -> list[str]:
        return [s.strip()[:300] for s in values if s.strip()]

@router.post("/analyze")
async def analyze_habitability(payload: HabitabilityRequest) -> dict[str, Any]:
    inputs = HabitabilityInputs(
        temperature=TemperatureInput(**payload.temperature.model_dump()) if payload.temperature else None,
        water=WaterInput(**payload.water.model_dump()) if payload.water else None,
        terrain=TerrainInput(**payload.terrain.model_dump()) if payload.terrain else None,
        risk=RiskInput(**payload.risk.model_dump()) if payload.risk else None,
    )
    assessment = assess_habitability(inputs, extra_limitations=(
        "Scores are heuristic screening outputs based on caller-supplied inputs; this service does not independently verify source data.",
        "A score is withheld unless the existing model's essential factors and coverage requirements are met.",
    ))
    return {
        "success": True,
        "region": payload.region.summary().model_dump(),
        "assessment": assessment.to_dict(),
        "evidence_sources": payload.evidence_sources,
        "classification": "derived_heuristic_from_caller_supplied_inputs",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
