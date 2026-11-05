"""Climate intelligence from the Open-Meteo historical archive (ERA5-based reanalysis)."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import numpy as np
from scipy import stats

from .common import cached, get_json, http, ok

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _daily(lat: float, lon: float, start: str, end: str, names: str) -> dict[str, list]:
    with http(25) as c:
        data = get_json(c, ARCHIVE, retries=1, params={"latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "daily": names, "timezone": "UTC"})
    return data.get("daily") or {}


def aridity_class(ai: float) -> str:
    return ("hyper-arid" if ai < 0.05 else "arid" if ai < 0.2 else "semi-arid" if ai < 0.5 else "dry sub-humid" if ai < 0.65 else "humid")


def summarize(daily: dict[str, list]) -> dict[str, Any]:
    """Pure function: daily series -> yearly stats, trends, monthly climatology."""
    times = [date.fromisoformat(t) for t in daily["time"]]
    arr = lambda k: np.array([np.nan if v is None else v for v in daily.get(k, [np.nan] * len(times))], dtype=float)  # noqa: E731
    temp, rain, et0 = arr("temperature_2m_mean"), arr("precipitation_sum"), arr("et0_fao_evapotranspiration")
    rh, wind, wdir, sm = arr("relative_humidity_2m_mean"), arr("wind_speed_10m_max"), arr("wind_direction_10m_dominant"), arr("soil_moisture_0_to_7cm_mean")
    years = np.array([t.year for t in times]); months = np.array([t.month for t in times])
    yearly = []
    for y in sorted(set(years.tolist())):
        m = years == y
        if np.isfinite(temp[m]).sum() < 330:
            continue
        r = rain[m]
        yearly.append({"year": int(y), "mean_temperature_c": round(float(np.nanmean(temp[m])), 2),
                       "rainfall_mm": round(float(np.nansum(r)), 0) if np.isfinite(r).sum() >= 330 else None,
                       "et0_mm": round(float(np.nansum(et0[m])), 0) if np.isfinite(et0[m]).sum() >= 330 else None})
    if len(yearly) < 3:
        raise ValueError("insufficient climate history")

    def trend(key: str) -> dict[str, Any] | None:
        pts = [(r["year"], r[key]) for r in yearly if r.get(key) is not None]
        if len(pts) < 6:
            return None
        lr = stats.linregress([p[0] for p in pts], [p[1] for p in pts])
        if not np.isfinite(lr.pvalue):
            return {"per_decade": 0.0, "p_value": None, "significant": False}
        return {"per_decade": round(float(lr.slope) * 10, 2), "p_value": round(float(lr.pvalue), 3), "significant": bool(lr.pvalue < 0.1)}

    def clim(a: np.ndarray, how: str) -> list[float | None]:
        out = []
        for mth in range(1, 13):
            m = months == mth
            if not np.isfinite(a[m]).any():
                out.append(None); continue
            if how == "sum":  # mean monthly total across years
                per_year = [np.nansum(a[m & (years == y)]) for y in set(years[m].tolist())]
                out.append(round(float(np.mean(per_year)), 1))
            else:
                out.append(round(float(np.nanmean(a[m])), 2))
        return out

    monthly = {"temperature_c": clim(temp, "mean"), "rainfall_mm": clim(rain, "sum"), "humidity_pct": clim(rh, "mean"), "wind_kmh": clim(wind, "mean")}
    rain_m = [v or 0 for v in monthly["rainfall_mm"]]
    total_rain = sum(rain_m)
    best = max(range(12), key=lambda i: sum(rain_m[(i + k) % 12] for k in range(3)))
    wet3 = sum(rain_m[(best + k) % 12] for k in range(3))
    ann_rain = [r["rainfall_mm"] for r in yearly if r["rainfall_mm"] is not None]
    ann_et0 = [r["et0_mm"] for r in yearly if r["et0_mm"] is not None]
    out: dict[str, Any] = {
        "period": f"{yearly[0]['year']}-{yearly[-1]['year']}", "years_used": len(yearly), "yearly": yearly,
        "mean_temperature_c": round(float(np.mean([r["mean_temperature_c"] for r in yearly])), 1),
        "annual_rainfall_mm": round(float(np.mean(ann_rain)), 0) if ann_rain else None,
        "annual_et0_mm": round(float(np.mean(ann_et0)), 0) if ann_et0 else None,
        "mean_humidity_pct": round(float(np.nanmean(rh)), 1) if np.isfinite(rh).any() else None,
        "trends": {"temperature_c": trend("mean_temperature_c"), "rainfall_mm": trend("rainfall_mm")},
        "monthly": monthly,
        "seasons": {"hottest_month": MONTHS[int(np.nanargmax([v if v is not None else -99 for v in monthly["temperature_c"]]))],
                    "coolest_month": MONTHS[int(np.nanargmin([v if v is not None else 99 for v in monthly["temperature_c"]]))],
                    "wettest_month": MONTHS[int(np.argmax(rain_m))], "driest_month": MONTHS[int(np.argmin(rain_m))],
                    "wettest_quarter": f"{MONTHS[best]}-{MONTHS[(best + 2) % 12]}",
                    "wettest_quarter_share_pct": round(100 * wet3 / total_rain, 0) if total_rain > 0 else None},
    }
    if out["annual_rainfall_mm"] and out["annual_et0_mm"]:
        ai = out["annual_rainfall_mm"] / out["annual_et0_mm"]
        out["aridity_index"], out["aridity_class"] = round(ai, 2), aridity_class(ai)
    if np.isfinite(wind).any():
        ok_ = np.isfinite(wind) & np.isfinite(wdir)
        if ok_.any():
            u = float(np.sum(wind[ok_] * np.sin(np.radians(wdir[ok_])))); v = float(np.sum(wind[ok_] * np.cos(np.radians(wdir[ok_]))))
            deg = (math.degrees(math.atan2(u, v)) + 360) % 360
            out["wind"] = {"mean_daily_max_kmh": round(float(np.nanmean(wind)), 1), "prevailing_direction": COMPASS[int((deg + 11.25) // 22.5) % 16], "prevailing_direction_deg": round(deg, 0)}
    if np.isfinite(sm).any():
        out["soil_moisture_m3m3"] = round(float(np.nanmean(sm)), 3)
    return out


def climate(lat: float, lon: float) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        y = date.today().year
        start, end = f"{y - 10}-01-01", f"{y - 1}-12-31"
        groups = ["temperature_2m_mean,precipitation_sum,et0_fao_evapotranspiration", "wind_speed_10m_max,wind_direction_10m_dominant",
                  "relative_humidity_2m_mean", "soil_moisture_0_to_7cm_mean"]
        def one(g: str):
            try:
                return _daily(lat, lon, start, end, g)
            except Exception:  # noqa: BLE001 - only the first (core) group is mandatory
                return None
        with ThreadPoolExecutor(4) as pool:
            parts = list(pool.map(one, groups))
        if parts[0] is None:
            raise RuntimeError("Open-Meteo archive unavailable")
        merged = dict(parts[0])
        for p in parts[1:]:
            if p:
                merged.update({k: v for k, v in p.items() if k != "time"})
        res = summarize(merged)
        res["source"] = "Open-Meteo Historical Weather API (ERA5 reanalysis, ~25 km grid, point at region centre)"
        return res
    return cached(("climate", round(lat, 2), round(lon, 2)), 6 * 3600, run)
