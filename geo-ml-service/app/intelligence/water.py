"""Water intelligence: mapped rivers/lakes (OSM), Sentinel-2 surface water, aridity-based stress."""
from __future__ import annotations

from typing import Any

from .common import cached, http, key_bbox, ok

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def osm_water(bbox: list[float]) -> dict[str, Any]:
    if bbox[2] - bbox[0] > 3 or bbox[3] - bbox[1] > 3:
        raise ValueError("region larger than 3 degrees; OSM water features not counted")
    b = f"({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]})"
    q = (f'[out:json][timeout:25];way["waterway"="river"]{b};out count;way["waterway"~"^(stream|canal)$"]{b};out count;'
         f'(way["natural"="water"]{b};relation["natural"="water"]{b};);out count;(way["landuse"="reservoir"]{b};way["water"="reservoir"]{b};);out count;')
    last: Exception | None = None
    for url in OVERPASS:
        try:
            with http(30) as c:
                r = c.post(url, data={"data": q}); r.raise_for_status()
            counts = [int((e.get("tags") or {}).get("total", 0)) for e in r.json().get("elements", []) if e.get("type") == "count"]
            if len(counts) == 4:
                return {"river_segments": counts[0], "streams_and_canals": counts[1], "lakes_and_water_bodies": counts[2], "reservoirs": counts[3],
                        "source": "OpenStreetMap via Overpass (counts of mapped features; depends on mapping completeness)"}
        except Exception as exc:  # noqa: BLE001 - try the mirror
            last = exc
    raise last or RuntimeError("Overpass unavailable")


def water_stress(climate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not climate or not ok(climate.get("aridity_index")):
        return None
    ai = climate["aridity_index"]
    level = "very high" if ai < 0.2 else "high" if ai < 0.5 else "moderate" if ai < 0.65 else "low"
    rain, et0 = climate.get("annual_rainfall_mm"), climate.get("annual_et0_mm")
    return {"level": level, "aridity_index": ai, "aridity_class": climate.get("aridity_class"), "annual_rainfall_mm": rain, "annual_et0_mm": et0,
            "climatic_water_balance_mm": round(rain - et0, 0) if ok(rain) and ok(et0) else None,
            "method": "UNEP aridity index = annual precipitation / reference evapotranspiration (ERA5, Open-Meteo). Climatic indicator only; it does not measure groundwater or supply infrastructure."}


def water(bbox: list[float], climate: dict[str, Any] | None, vegetation: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        out["mapped_features"] = cached(("osmw", key_bbox(bbox)), 24 * 3600, lambda: osm_water(bbox))
    except Exception:  # noqa: BLE001
        pass
    sw = ((vegetation or {}).get("ndvi") or {}).get("surface_water")
    if sw:
        out["surface_water"] = {"water_fraction_pct": sw["pct_of_valid"], "area_km2": sw["area_km2"], "scene_date": vegetation["scene"]["date"], "source": "Sentinel-2 L2A (NDWI / SCL), cloud-free pixels only"}
    ws = water_stress(climate)
    if ws:
        out["stress"] = ws
    if not out:
        raise RuntimeError("no water data sources responded")
    return out
