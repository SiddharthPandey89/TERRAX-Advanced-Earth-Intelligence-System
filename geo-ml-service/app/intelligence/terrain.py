"""Terrain intelligence: elevation, slope, aspect, classification from Copernicus DEM 30 m."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .common import cached, colorize, get_json, http, key_bbox, ok, overlay


def slope_aspect(dem: np.ndarray, dx_m: float, dy_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Slope (degrees) and aspect (degrees clockwise from north, direction the slope faces)."""
    if dem.shape[0] < 3 or dem.shape[1] < 3:
        raise ValueError("DEM too small for slope")
    dz_dy, dz_dx = np.gradient(dem, dy_m, dx_m)  # rows increase southwards
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    aspect = (np.degrees(np.arctan2(-dz_dx, dz_dy)) + 360.0) % 360.0
    aspect = np.where(np.hypot(dz_dx, dz_dy) < 1e-6, np.nan, aspect)
    return slope, aspect


def slope_class(deg: float) -> str:
    return "flat" if deg < 2 else "gentle" if deg < 5 else "moderate" if deg < 15 else "steep" if deg < 30 else "very steep"


def analyze_dem(dem: np.ndarray, bbox: list[float]) -> dict[str, Any]:
    w, s, e, n = bbox
    rows, cols = dem.shape
    lat = (s + n) / 2
    dx = (e - w) * 111320.0 * math.cos(math.radians(lat)) / cols
    dy = (n - s) * 110574.0 / rows
    slope, aspect = slope_aspect(dem, dx, dy)
    valid = np.isfinite(dem)
    if valid.sum() < 9:
        raise ValueError("no DEM coverage")
    relief = float(np.nanmax(dem) - np.nanmin(dem))
    asp = aspect[np.isfinite(aspect)]
    names = ["N", "E", "S", "W"]
    shares = {}
    if asp.size:
        idx = (((asp + 45) % 360) // 90).astype(int)
        shares = {names[i]: round(100 * float((idx == i).mean()), 0) for i in range(4)}
    sl = slope[np.isfinite(slope)]
    if sl.size < 9:
        raise ValueError("no valid slope cells")
    res = {
        "elevation_m": {"min": round(float(np.nanmin(dem)), 0), "mean": round(float(np.nanmean(dem)), 0), "max": round(float(np.nanmax(dem)), 0)},
        "relief_m": round(relief, 0), "mean_slope_deg": round(float(sl.mean()), 1), "max_slope_deg": round(float(np.percentile(sl, 99)), 1),
        "slope_class": slope_class(float(sl.mean())),
        "slope_distribution_pct": {k: round(100 * float(((sl >= lo) & (sl < hi)).mean()), 0) for k, (lo, hi) in
                                   {"flat (<2)": (0, 2), "gentle (2-5)": (2, 5), "moderate (5-15)": (5, 15), "steep (15-30)": (15, 30), "very steep (>30)": (30, 91)}.items()},
        "aspect_share_pct": shares, "grid": f"{rows}x{cols} cells (~{dx:.0f} m x {dy:.0f} m)",
        "terrain_class": "plain" if relief < 50 else "undulating plain" if relief < 150 else "hills" if relief < 600 else "mountains",
    }
    stops = [(float(np.nanmin(dem)), (34, 139, 94)), (float(np.nanmin(dem)) + relief * 0.4, (219, 205, 120)), (float(np.nanmin(dem)) + relief * 0.75, (160, 110, 70)), (float(np.nanmax(dem)) + 1e-6, (245, 245, 245))]
    res["_dem_overlay"] = overlay("elevation", "Elevation", colorize(dem, stops, alpha=170), bbox,
                                  [{"color": "#228b5e", "label": f"{np.nanmin(dem):.0f} m"}, {"color": "#f5f5f5", "label": f"{np.nanmax(dem):.0f} m"}])
    res["_slope_overlay"] = overlay("slope", "Slope", colorize(slope, [(0, (60, 180, 120)), (5, (230, 220, 90)), (15, (240, 150, 60)), (30, (200, 50, 50))], alpha=180), bbox,
                                    [{"color": "#3cb478", "label": "0°"}, {"color": "#f0963c", "label": "15°"}, {"color": "#c83232", "label": "30°+"}])
    return res


def _dem_stac(bbox: list[float]) -> tuple[np.ndarray, str]:
    from rasterio.enums import Resampling
    from .raster_io import Grid, read_mosaic, stac_search
    items = stac_search("cop-dem-glo-30", bbox, limit=20, sort_desc=False)
    hrefs = [i["assets"]["data"]["href"] for i in items if "data" in i.get("assets", {})]
    dem = read_mosaic(hrefs, Grid(bbox, native_m=30.0), Resampling.bilinear) if hrefs else None
    if dem is None:
        raise RuntimeError("no DEM tiles cover the region")
    return dem, "Copernicus DEM GLO-30 (30 m) via Earth Search"


def _dem_grid(bbox: list[float], n: int = 9) -> tuple[np.ndarray, str]:
    w, s, e, nn = bbox
    xs = [w + (i + 0.5) * (e - w) / n for i in range(n)]
    ys = [nn - (j + 0.5) * (nn - s) / n for j in range(n)]
    lats = [y for y in ys for _ in xs]; lons = [x for _ in ys for x in xs]
    with http(20) as c:
        d = get_json(c, "https://api.open-meteo.com/v1/elevation", params={"latitude": ",".join(f"{v:.5f}" for v in lats), "longitude": ",".join(f"{v:.5f}" for v in lons)})
    arr = np.array(d["elevation"], dtype="float64").reshape(n, n)
    return arr, f"Open-Meteo elevation API ({n}x{n} sample grid, coarse)"


def terrain(bbox: list[float]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        try:
            dem, src = _dem_stac(bbox)
        except Exception:  # noqa: BLE001 - alternative public provider
            dem, src = _dem_grid(bbox)
        res = analyze_dem(dem, bbox)
        res["source"] = src
        return res
    return cached(("terrain", key_bbox(bbox)), 24 * 3600, run)
