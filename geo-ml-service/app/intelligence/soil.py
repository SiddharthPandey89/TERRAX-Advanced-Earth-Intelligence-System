"""Soil intelligence (ISRIC SoilGrids v2.0) with fertility index and texture class."""
from __future__ import annotations

from typing import Any

from .common import cached, get_json, http, ok

BASE = "https://rest.isric.org/soilgrids/v2.0"
PROPS = ("clay", "sand", "silt", "phh2o", "soc", "nitrogen", "cec")
DEPTHS = ("0-5cm", "5-15cm", "15-30cm")


def texture_class(clay: float, sand: float, silt: float) -> str:
    if clay >= 40: return "clay" if sand < 45 and silt < 40 else "sandy clay" if sand >= 45 else "silty clay"
    if clay >= 27: return "clay loam" if sand < 20 or sand < 45 and silt >= 28 else "sandy clay loam" if sand >= 45 else "clay loam"
    if silt >= 80 and clay < 12: return "silt"
    if silt >= 50 and clay < 27: return "silt loam"
    if sand >= 85: return "sand"
    if sand >= 70: return "loamy sand"
    if clay >= 20 and sand >= 45: return "sandy clay loam"
    if sand >= 52: return "sandy loam"
    return "loam"


def _ramp(x: float, a: float, b: float, c: float, d: float) -> float:
    return 0.0 if x <= a or x >= d else (x - a) / (b - a) if x < b else 1.0 if x <= c else (d - x) / (d - c)


def fertility(p: dict[str, float | None]) -> dict[str, Any]:
    f = {}
    if ok(p.get("ph")): f["pH"] = _ramp(p["ph"], 4.5, 5.8, 7.6, 9.0)
    if ok(p.get("soc")): f["organic carbon"] = min(1.0, p["soc"] / 20.0)       # g/kg
    if ok(p.get("nitrogen")): f["nitrogen"] = min(1.0, p["nitrogen"] / 2.0)    # g/kg
    if ok(p.get("cec")): f["cation exchange"] = min(1.0, p["cec"] / 25.0)      # cmol/kg
    if len(f) < 3:
        return {"status": "withheld", "reason": "Fewer than three fertility inputs were returned by SoilGrids."}
    score = round(100 * sum(f.values()) / len(f), 0)
    return {"status": "scored", "score": score, "class": "low" if score < 35 else "moderate" if score < 65 else "high",
            "components": {k: round(v, 2) for k, v in f.items()},
            "method": "Mean of 0-1 scores: pH (ideal 5.8-7.6), organic carbon (20 g/kg = 1), nitrogen (2 g/kg = 1), CEC (25 cmol/kg = 1). Screening index, not a lab fertility test."}


def soil(lat: float, lon: float) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        params = [("lon", lon), ("lat", lat), ("value", "mean")] + [("property", x) for x in PROPS] + [("depth", d) for d in DEPTHS]
        with http(30) as c:
            layers = ((get_json(c, f"{BASE}/properties/query", retries=1, params=params).get("properties") or {}).get("layers")) or []
            try:
                cls = get_json(c, f"{BASE}/classification/query", retries=0, params={"lon": lon, "lat": lat, "number_classes": 3})
            except Exception:  # noqa: BLE001 - classification is optional
                cls = None
        vals: dict[str, float | None] = {}
        for lay in layers:
            d = (lay.get("unit_measure") or {}).get("d_factor") or 1
            xs = [dep["values"].get("mean") for dep in lay.get("depths", []) if (dep.get("values") or {}).get("mean") is not None]
            if xs:
                vals[lay["name"]] = round(sum(xs) / len(xs) / d, 2)
        if not vals:
            raise ValueError("SoilGrids returned no values (location may be water or unmapped)")
        p = {"clay_pct": vals.get("clay"), "sand_pct": vals.get("sand"), "silt_pct": vals.get("silt"), "ph": vals.get("phh2o"),
             "soc": vals.get("soc"), "nitrogen": vals.get("nitrogen"), "cec": vals.get("cec")}
        out: dict[str, Any] = {"properties": {"clay_pct": p["clay_pct"], "sand_pct": p["sand_pct"], "silt_pct": p["silt_pct"], "ph": p["ph"], "organic_carbon_g_per_kg": p["soc"],
                                              "nitrogen_g_per_kg": p["nitrogen"], "cec_cmol_per_kg": p["cec"]}, "depth": "0-30 cm (mean of 0-5, 5-15, 15-30 cm)"}
        if all(ok(p[k]) for k in ("clay_pct", "sand_pct", "silt_pct")):
            out["texture_class"] = texture_class(p["clay_pct"], p["sand_pct"], p["silt_pct"])
        if isinstance(cls, dict) and cls.get("wrb_class_name"):
            out["classification"] = {"wrb_class": cls["wrb_class_name"], "alternatives": [{"class": a[0], "probability_pct": a[1]} for a in (cls.get("wrb_class_probability") or [])[:3]]}
        out["fertility"] = fertility({"ph": p["ph"], "soc": p["soc"], "nitrogen": p["nitrogen"], "cec": p["cec"]})
        out["source"] = "ISRIC SoilGrids v2.0 (250 m global model; point sample at region centre; modelled, not surveyed)"
        return out
    return cached(("soil", round(lat, 3), round(lon, 3)), 7 * 24 * 3600, run)
