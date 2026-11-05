"""Transparent regional suitability: habitability and agriculture from the real indicators gathered."""
from __future__ import annotations

from typing import Any

from .common import ok

CROPS = {  # (temp trapezoid C, rainfall trapezoid mm/yr, pH trapezoid): FAO-style screening ranges
    "Wheat": ((3, 12, 22, 30), (300, 450, 900, 1500), (5.5, 6.0, 7.5, 8.5)),
    "Rice": ((16, 22, 30, 37), (800, 1200, 2500, 4000), (4.5, 5.5, 7.0, 8.5)),
    "Maize": ((10, 18, 27, 35), (400, 600, 1200, 2000), (5.2, 5.8, 7.2, 8.2)),
    "Soybean": ((12, 20, 28, 35), (450, 600, 1200, 1800), (5.2, 6.0, 7.2, 8.2)),
    "Cotton": ((15, 21, 32, 38), (500, 700, 1300, 1800), (5.5, 6.0, 8.0, 9.0)),
    "Sorghum / millet": ((12, 22, 33, 40), (250, 400, 900, 1400), (5.0, 5.5, 8.0, 9.0)),
    "Chickpea / pulses": ((8, 15, 28, 35), (300, 400, 800, 1200), (5.5, 6.0, 8.0, 9.0)),
}


def ramp(x: float, a: float, b: float, c: float, d: float) -> float:
    return 0.0 if x <= a or x >= d else (x - a) / (b - a) if x < b else 1.0 if x <= c else (d - x) / (d - c)


def agriculture(climate: dict | None, soil: dict | None) -> dict[str, Any] | None:
    ph = ((soil or {}).get("properties") or {}).get("ph")
    if not climate or not ok(climate.get("mean_temperature_c")) or not ok(climate.get("annual_rainfall_mm")) or not ok(ph):
        return None
    t, r = climate["mean_temperature_c"], climate["annual_rainfall_mm"]
    crops = []
    for name, (tt, rr, pp) in CROPS.items():
        s = {"temperature": ramp(t, *tt), "rainfall": ramp(r, *rr), "soil pH": ramp(ph, *pp)}
        score = round(100 * (s["temperature"] * s["rainfall"] * s["soil pH"]) ** (1 / 3), 0)  # limiting-factor geometric mean
        crops.append({"crop": name, "score": score, "class": "low" if score < 35 else "moderate" if score < 65 else "high", "limiting_factor": min(s, key=s.get)})
    crops.sort(key=lambda c: -c["score"])
    fert = (soil or {}).get("fertility") or {}
    overall = round(sum(c["score"] for c in crops[:3]) / 3, 0)
    return {"score": overall, "class": "low" if overall < 35 else "moderate" if overall < 65 else "high", "crops": crops,
            "soil_fertility_class": fert.get("class"),
            "method": "Per crop: geometric mean of temperature, rainfall and soil-pH suitability (0-1 trapezoids from FAO-style ecological ranges); overall = mean of the best three crops. Irrigation, slope, salinity and market access are not considered."}


def habitability(c: dict | None, w: dict | None, v: dict | None, s: dict | None, t: dict | None) -> dict[str, Any]:
    comp: dict[str, tuple[float, float, str]] = {}  # name -> (score 0-1, weight, how)
    if c and ok(c.get("mean_temperature_c")):
        comp["Thermal comfort"] = (ramp(c["mean_temperature_c"], 2, 12, 26, 36), 0.25, f"annual mean {c['mean_temperature_c']} C (ideal 12-26 C)")
    if c and ok(c.get("aridity_index")):
        comp["Water balance"] = (min(1.0, c["aridity_index"] / 0.65), 0.25, f"aridity index {c['aridity_index']} ({c.get('aridity_class')}); humid >= 0.65")
    if v and v.get("ndvi"):
        comp["Vegetation"] = (min(1.0, max(0.0, v["ndvi"]["mean_ndvi"] / 0.5)), 0.15, f"mean NDVI {v['ndvi']['mean_ndvi']} (0.5 = 1)")
    if t and ok(t.get("mean_slope_deg")):
        comp["Terrain"] = (ramp(t["mean_slope_deg"], -1, 0, 8, 30), 0.15, f"mean slope {t['mean_slope_deg']} deg (<=8 deg ideal)")
    fert = (s or {}).get("fertility") or {}
    if fert.get("status") == "scored":
        comp["Soil fertility"] = (fert["score"] / 100.0, 0.10, f"fertility index {fert['score']:.0f}/100")
    sw = (w or {}).get("surface_water") or {}
    mapped = (w or {}).get("mapped_features") or {}
    if ok(sw.get("water_fraction_pct")) or mapped:
        has = (ok(sw.get("water_fraction_pct")) and sw["water_fraction_pct"] > 0.2) or mapped.get("river_segments", 0) > 0 or mapped.get("lakes_and_water_bodies", 0) > 0
        comp["Surface water presence"] = (1.0 if has else 0.3, 0.10, "rivers/lakes or surface water detected" if has else "no mapped rivers/lakes and negligible detected surface water")
    needed = {"Thermal comfort", "Water balance"}
    if len(comp) < 4 or not needed <= set(comp):
        return {"status": "withheld", "reason": "Needs climate (temperature and aridity) plus at least two other indicators; not enough real data returned."}
    wsum = sum(x[1] for x in comp.values())
    score = round(100 * sum(x[0] * x[1] for x in comp.values()) / wsum, 0)
    return {"status": "scored", "score": score, "class": "low" if score < 35 else "moderate" if score < 60 else "high",
            "components": [{"name": k, "score": round(100 * v_[0], 0), "weight_pct": round(100 * v_[1] / wsum, 0), "basis": v_[2]} for k, v_ in comp.items()],
            "method": "Weighted mean of the 0-100 component scores shown (weights renormalised over available indicators). A transparent screening index of environmental suitability for settlement; it ignores infrastructure, hazards and legal factors."}
