"""Evidence-weighted prospectivity API; outputs are screening potentials, not discoveries."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.region import GeographicRegion
from app.prospectivity.auto import MINERALS, run_auto
from app.prospectivity.engine import ProspectivityTarget, TargetRequest, analyze_prospectivity

router = APIRouter(prefix="/prospectivity", tags=["prospectivity"])

class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion: str = Field(min_length=1, max_length=64)
    favourability: float = Field(ge=0, le=1)
    source: str = Field(min_length=1, max_length=300)
    evidence_type: Literal["observed", "interpreted", "modelled"]
    coverage: float | None = Field(default=None, ge=0, le=1)
    description: str | None = Field(default=None, max_length=500)

class TargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mineral", "petroleum", "gas"]
    commodity: str | None = Field(default=None, min_length=1, max_length=64)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=500)

class OccurrenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commodity: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=300)
    name: str | None = Field(default=None, max_length=200)
    reported_status: str | None = Field(default=None, max_length=120)

class ProspectivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: GeographicRegion
    targets: list[TargetInput] = Field(min_length=1, max_length=20)
    reported_occurrences: list[OccurrenceInput] = Field(default_factory=list, max_length=100)

@router.post("/analyze")
async def analyze(payload: ProspectivityRequest) -> dict[str, Any]:
    try:
        targets = [TargetRequest(
            target=ProspectivityTarget(kind=t.kind, commodity=t.commodity),
            evidence=[item.model_dump() for item in t.evidence],
        ) for t in payload.targets]
        report = analyze_prospectivity(targets, [o.model_dump() for o in payload.reported_occurrences])
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)[:300]) from exc
    return {"success": True, "region": payload.region.summary().model_dump(), "report": report.to_dict(),
            "classification": "derived_evidence_weighted_screening_potential",
            "discovery_claim": False}


class AutoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: GeographicRegion
    minerals: list[str] | None = Field(default=None, max_length=20)

@router.post("/auto")
async def analyze_auto(payload: AutoRequest) -> dict[str, Any]:
    """Collect public geology data for the region and assess minerals, petroleum and gas."""
    summary = payload.region.summary()
    west, south, east, north = summary.bbox
    if payload.region.point is not None:
        west, east, south, north = west - 0.05, east + 0.05, south - 0.05, north + 0.05
    if east - west > 10 or north - south > 10:
        raise HTTPException(422, "Region is larger than 10 degrees; select a smaller area.")
    geometry = payload.region.geometry.model_dump() if payload.region.geometry else None
    wanted = [m.strip().lower() for m in payload.minerals] if payload.minerals else None
    if wanted and not [m for m in wanted if m in MINERALS]:
        raise HTTPException(422, f"Supported minerals: {', '.join(MINERALS)}.")
    import asyncio
    try:
        result = await asyncio.wait_for(asyncio.to_thread(run_auto, [west, south, east, north], geometry, wanted), 90.0)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Geology providers did not respond in time; try again shortly.")
    result["region"] = summary.model_dump()
    return result
