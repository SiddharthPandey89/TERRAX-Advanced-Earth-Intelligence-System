"""Per-module regional intelligence. Each module is requested independently so a slow or
failed provider never blocks the others. Provider failures return HTTP 200 with
``available: false`` and a reason (no fabricated values)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.intelligence import suitability as suit
from app.intelligence.climate import climate as get_climate
from app.intelligence.satellite import vegetation as get_vegetation
from app.intelligence.soil import soil as get_soil
from app.intelligence.terrain import terrain as get_terrain
from app.intelligence.water import water as get_water

router = APIRouter(prefix="/environment", tags=["environment"])
log = logging.getLogger("environment")
Module = Literal["climate", "terrain", "soil", "vegetation", "water", "suitability"]
BUDGET = {"vegetation": 85.0, "terrain": 40.0, "water": 45.0, "suitability": 100.0}


class ModuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bbox: list[float] = Field(min_length=4, max_length=4)
    module: Module
    geometry: dict[str, Any] | None = None


def _try(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - dependent modules degrade gracefully
        log.info("sub-module failed: %s", exc)
        return None


def _split(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overlays = list(data.pop("_overlays", []))
    for k in ("_dem_overlay", "_slope_overlay"):
        if k in data:
            overlays.append(data.pop(k))
    return data, overlays


def compute(module: str, bbox: list[float], geometry: dict[str, Any] | None = None) -> dict[str, Any]:
    lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
    if module == "climate":
        data = get_climate(lat, lon)
    elif module == "terrain":
        data = get_terrain(bbox)
    elif module == "soil":
        data = get_soil(lat, lon)
    elif module == "vegetation":
        data = get_vegetation(bbox, geometry)
    elif module == "water":
        data = get_water(bbox, _try(lambda: get_climate(lat, lon)), _try(lambda: get_vegetation(bbox, geometry)))
    else:
        c, s = _try(lambda: get_climate(lat, lon)), _try(lambda: get_soil(lat, lon))
        v, t = _try(lambda: get_vegetation(bbox, geometry)), _try(lambda: get_terrain(bbox))
        w = _try(lambda: get_water(bbox, c, v))
        data = {"habitability": suit.habitability(c, w, v, s, t), "agriculture": suit.agriculture(c, s)}
        if data["agriculture"] is None:
            data["agriculture"] = {"status": "withheld"}
        if (s or {}).get("fertility"):
            data["soil_fertility"] = s["fertility"]
    return _split(dict(data)) if isinstance(data, dict) else ({}, [])  # type: ignore[return-value]


@router.post("/module")
async def run_module(payload: ModuleRequest) -> dict[str, Any]:
    w, s, e, n = payload.bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise HTTPException(422, "Invalid bbox.")
    if payload.module in ("vegetation", "terrain", "water") and (e - w > 5 or n - s > 5):
        return {"module": payload.module, "available": False, "reason": "Region is larger than 5 degrees; select a smaller area for raster analysis."}
    try:
        data, overlays = await asyncio.wait_for(asyncio.to_thread(compute, payload.module, payload.bbox, payload.geometry), BUDGET.get(payload.module, 45.0))
    except asyncio.TimeoutError:
        return {"module": payload.module, "available": False, "reason": "The data provider did not respond in time. Try again shortly."}
    except Exception as exc:  # noqa: BLE001
        log.warning("module %s failed: %s", payload.module, exc)
        return {"module": payload.module, "available": False, "reason": f"Data provider unavailable ({type(exc).__name__}: {str(exc)[:120]})."}
    return {"module": payload.module, "available": True, "data": data, "overlays": overlays}
