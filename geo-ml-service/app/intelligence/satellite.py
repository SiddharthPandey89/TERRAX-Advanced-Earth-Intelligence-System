"""Vegetation, forest and surface-water statistics for the selected region.

* Sentinel-2 L2A (Earth Search STAC, open COGs): cloud-masked NDVI / NDWI on the exact region grid.
* ESA WorldCover 2021 (10 m): the land-cover classification used for FOREST (tree cover) area.
  NDVI thresholds are used only as a greenness indicator, never as proof of forest.
Every statistic is computed from raster pixels inside the selected polygon/bbox; clouds,
no-data and outside-region cells are excluded and the valid-data coverage is reported separately.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from pyproj import Geod
from rasterio.enums import Resampling
from shapely.geometry import box, shape

from .common import cached, colorize, key_bbox, overlay
from .raster_io import Grid, coverage, read_grid, read_mosaic, stac_search

WC = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice", 80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}
FOREST = (10, 95)
OTHER_VEG = (20, 30, 40, 90, 100)
NONVEG = (50, 60, 70, 80)
VALID_SCL = (4, 5, 6, 7)
NDVI_VEG, NDVI_SPARSE = 0.30, 0.15
GEOD = Geod(ellps="WGS84")


def region_area_km2(bbox: list[float], geometry: dict | None) -> float:
    geom = shape(geometry).intersection(box(*bbox)) if geometry else box(*bbox)
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def reflectance(dn: np.ndarray, asset: dict[str, Any], props: dict[str, Any]) -> np.ndarray:
    """DN -> surface reflectance using the asset's raster:bands scale/offset (processing baseline >= 4 carries a -0.1 offset)."""
    rb = (asset.get("raster:bands") or [{}])[0]
    scale = rb.get("scale", 0.0001)
    offset = rb.get("offset")
    if offset is None:
        base = str(props.get("s2:processing_baseline", "0"))
        try:
            offset = -0.1 if float(base) >= 4.0 and not props.get("earthsearch:boa_offset_applied") else 0.0
        except ValueError:
            offset = 0.0
    return dn * scale + offset


def indices(red: np.ndarray, nir: np.ndarray, green: np.ndarray, scl: np.ndarray) -> dict[str, np.ndarray]:
    """Pure function: reflectance arrays -> masked NDVI/NDWI + water and valid masks (clouds, shadow, snow, no-data excluded)."""
    valid = np.isin(scl, VALID_SCL) & np.isfinite(red) & np.isfinite(nir) & np.isfinite(green) & ((red + nir) > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(valid, (nir - red) / (nir + red), np.nan)
        ndwi = np.where(valid, (green - nir) / (green + nir), np.nan)
    water = valid & ((ndwi > 0.15) | (scl == 6))
    return {"ndvi": ndvi, "ndwi": ndwi, "water": water, "valid": valid}


def landcover_report(wc: np.ndarray, inside: np.ndarray, grid: Grid) -> dict[str, Any]:
    """Areas and shares from the WorldCover classes inside the region. Denominator = valid classified area."""
    cls = np.where(np.isfinite(wc), wc, 0).astype(int)
    valid = inside & (cls > 0)
    n_valid = int(valid.sum())
    if n_valid == 0:
        raise ValueError("no valid land-cover pixels in region")
    km2 = lambda mask: round(float((mask & valid).sum() * grid.cell_km2), 3)  # noqa: E731
    pct = lambda mask: round(100.0 * float((mask & valid).sum()) / n_valid, 1)  # noqa: E731
    grp = lambda codes: np.isin(cls, codes)  # noqa: E731
    out = {"classified_area_km2": round(n_valid * grid.cell_km2, 3), "valid_classified_pct_of_region": round(100.0 * n_valid / max(1, int(inside.sum())), 1),
           "forest": {"area_km2": km2(grp(FOREST)), "pct": pct(grp(FOREST)), "definition": "ESA WorldCover classes Tree cover + Mangroves"},
           "other_vegetation": {"area_km2": km2(grp(OTHER_VEG)), "pct": pct(grp(OTHER_VEG)), "definition": "Shrubland, grassland, cropland, herbaceous wetland, moss/lichen"},
           "non_vegetated": {"area_km2": km2(grp(NONVEG)), "pct": pct(grp(NONVEG)), "definition": "Built-up, bare/sparse, snow/ice, permanent water"},
           "classes": []}
    for c in sorted(WC):
        if (grp((c,)) & valid).any():
            out["classes"].append({"code": c, "name": WC[c], "area_km2": km2(grp((c,))), "pct": pct(grp((c,)))})
    out["classes"].sort(key=lambda x: -x["pct"])
    return out


def greenness_report(arr: dict[str, np.ndarray], inside: np.ndarray, grid: Grid) -> dict[str, Any]:
    """NDVI statistics over cloud-free land pixels inside the region; clouds/invalid are NOT counted as non-vegetated."""
    n_inside = int(inside.sum())
    valid = arr["valid"] & inside
    n_valid = int(valid.sum())
    if n_valid < 25:
        raise ValueError("too few cloud-free pixels inside the region")
    land = valid & ~arr["water"]
    n_land = int(land.sum())
    ndvi = arr["ndvi"][land] if n_land else np.array([0.0])
    km2 = lambda m: round(float(m.sum() * grid.cell_km2), 3)  # noqa: E731
    share = lambda m: round(100.0 * float(m.sum()) / max(1, n_land), 1)  # noqa: E731
    green = land & (arr["ndvi"] >= NDVI_VEG); sparse = land & (arr["ndvi"] >= NDVI_SPARSE) & (arr["ndvi"] < NDVI_VEG); bare = land & (arr["ndvi"] < NDVI_SPARSE)
    return {"valid_cloud_free_pct_of_region": round(100.0 * n_valid / max(1, n_inside), 1), "cloud_or_invalid_pct_of_region": round(100.0 * (1 - n_valid / max(1, n_inside)), 1),
            "mean_ndvi": round(float(ndvi.mean()), 3), "median_ndvi": round(float(np.median(ndvi)), 3), "p10_p90": [round(float(np.percentile(ndvi, 10)), 2), round(float(np.percentile(ndvi, 90)), 2)],
            "greenness": {"green_vegetation": {"area_km2": km2(green), "pct": share(green), "rule": f"NDVI >= {NDVI_VEG}"},
                          "sparse_vegetation": {"area_km2": km2(sparse), "pct": share(sparse), "rule": f"{NDVI_SPARSE} <= NDVI < {NDVI_VEG}"},
                          "bare_or_built": {"area_km2": km2(bare), "pct": share(bare), "rule": f"NDVI < {NDVI_SPARSE}"}},
            "surface_water": {"area_km2": km2(valid & arr["water"]), "pct_of_valid": round(100.0 * float((valid & arr["water"]).sum()) / n_valid, 2), "method": "NDWI > 0.15 or Sentinel-2 SCL water class"},
            "denominator_note": "Percentages are of cloud-free land pixels (water excluded); clouds, shadow, snow and no-data are excluded, not counted as non-vegetated."}


def change_report(now: dict[str, np.ndarray], prev: dict[str, np.ndarray], inside: np.ndarray, tree: np.ndarray | None) -> dict[str, Any] | None:
    both = now["valid"] & prev["valid"] & inside & ~now["water"] & ~prev["water"]
    if both.sum() < 25:
        return None
    d = now["ndvi"] - prev["ndvi"]
    out = {"mean_ndvi_change": round(float(d[both].mean()), 3), "pixels_compared": int(both.sum()), "declined_pct": round(100 * float((d[both] < -0.2).mean()), 1), "improved_pct": round(100 * float((d[both] > 0.2).mean()), 1)}
    if tree is not None and (both & tree).sum() >= 25:
        out["tree_pixels_with_decline_pct"] = round(100 * float((d[both & tree] < -0.2).mean()), 1)
    return out


def _arrays(item: dict[str, Any], grid: Grid) -> dict[str, np.ndarray]:
    a, p = item["assets"], item["properties"]
    f = lambda k, res=Resampling.bilinear: read_grid(a[k]["href"], grid, res)  # noqa: E731
    red, nir, green = (reflectance(f(k), a[k], p) for k in ("red", "nir", "green"))
    scl = np.nan_to_num(f("scl", Resampling.nearest), nan=0).astype(int)
    return indices(red, nir, green, scl)


def _scenes(bbox: list[float], dt: str, max_cloud: int, need: int = 8) -> list[dict[str, Any]]:
    items = stac_search("sentinel-2-l2a", bbox, datetime=dt, limit=50, query={"eo:cloud_cover": {"lt": max_cloud}})
    items = [i for i in items if all(k in i.get("assets", {}) for k in ("red", "nir", "green", "scl")) and coverage(i, bbox) > 0.05]
    items.sort(key=lambda i: (round(coverage(i, bbox), 1), i["properties"]["datetime"]), reverse=True)
    return items[:need]


def _composite(items: list[dict[str, Any]], grid: Grid, inside: np.ndarray, min_valid: float = 0.4) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]] | None:
    """Best scene first; fill remaining invalid cells from other scenes within 12 days (e.g. region spans two tiles)."""
    base = None
    used: list[dict[str, Any]] = []
    for it in items:
        try:
            arr = _arrays(it, grid)
        except Exception:  # noqa: BLE001 - unreadable scene, try the next
            continue
        if base is None:
            if (arr["valid"] & inside).sum() / max(1, inside.sum()) >= min_valid:
                base, used = arr, [it]
            continue
        d0 = datetime.fromisoformat(used[0]["properties"]["datetime"].replace("Z", "+00:00"))
        d1 = datetime.fromisoformat(it["properties"]["datetime"].replace("Z", "+00:00"))
        if abs((d1 - d0).days) > 12 or (base["valid"] | ~inside).all():
            continue
        fill = ~base["valid"] & arr["valid"]
        if fill.any():
            for k in ("ndvi", "ndwi"):
                base[k] = np.where(fill, arr[k], base[k])
            base["water"] = np.where(fill, arr["water"], base["water"]); base["valid"] = base["valid"] | fill; used.append(it)
    return (base, used) if base is not None else None


def _worldcover(grid: Grid) -> np.ndarray | None:
    try:
        items = stac_search("esa-worldcover", grid.bbox, datetime="2021-01-01/2021-12-31", limit=10, sort_desc=False)
        hrefs = [i["assets"]["map"]["href"] for i in items if "map" in i.get("assets", {})]
        return read_mosaic(hrefs, grid, Resampling.nearest, nodata=0) if hrefs else None
    except Exception:  # noqa: BLE001 - classification is optional; forest is then NOT reported
        return None


def _class_overlay(wc: np.ndarray | None, arr: dict[str, np.ndarray], inside: np.ndarray, bbox: list[float]) -> dict[str, Any]:
    rgba = np.zeros(arr["ndvi"].shape + (4,), dtype=np.uint8)
    if wc is not None:
        cls = np.where(np.isfinite(wc), wc, 0).astype(int)
        for codes, rgb in ((FOREST, (11, 110, 45)), (OTHER_VEG, (168, 207, 84)), ((50, 60, 70), (205, 178, 130)), ((80,), (40, 140, 255))):
            rgba[np.isin(cls, codes) & inside] = (*rgb, 205)
        legend = [{"color": "#0b6e2d", "label": "Forest (tree cover)"}, {"color": "#a8cf54", "label": "Other vegetation"}, {"color": "#cdb282", "label": "Built / bare"}, {"color": "#288cff", "label": "Water"}]
        return overlay("vegmap", "Forest & vegetation map", rgba, bbox, legend, "ESA WorldCover 2021 classes (10 m)")
    v, n = arr["valid"] & inside, arr["ndvi"]
    for m, rgb in ((v & ~arr["water"] & (n >= 0.6), (11, 110, 45)), (v & ~arr["water"] & (n >= NDVI_VEG) & (n < 0.6), (110, 180, 70)), (v & ~arr["water"] & (n >= NDVI_SPARSE) & (n < NDVI_VEG), (214, 205, 110)), (v & ~arr["water"] & (n < NDVI_SPARSE), (205, 178, 130)), (v & arr["water"], (40, 140, 255))):
        rgba[m] = (*rgb, 205)
    legend = [{"color": "#0b6e2d", "label": "Dense vegetation (NDVI>=0.6)"}, {"color": "#6eb446", "label": "Vegetation (0.3-0.6)"}, {"color": "#d6cd6e", "label": "Sparse (0.15-0.3)"}, {"color": "#cdb282", "label": "Bare / built"}, {"color": "#288cff", "label": "Water"}]
    return overlay("vegmap", "Vegetation map (not a forest map)", rgba, bbox, legend, "Sentinel-2 NDVI classes; clouds transparent")


def vegetation(bbox: list[float], geometry: dict | None = None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        grid = Grid(bbox)
        inside = grid.inside_mask(geometry)
        today = date.today()
        scenes = _scenes(bbox, f"{(today - timedelta(days=120)).isoformat()}/{today.isoformat()}", 35)
        if not scenes:
            scenes = _scenes(bbox, f"{(today - timedelta(days=365)).isoformat()}/{today.isoformat()}", 50)
        comp = _composite(scenes, grid, inside)
        if not comp:
            raise RuntimeError("no usable cloud-free Sentinel-2 scene found for this region")
        arr, used = comp
        when = used[0]["properties"]["datetime"][:10]
        out: dict[str, Any] = {
            "region": {"area_km2": round(region_area_km2(bbox, geometry), 2), "grid": f"{grid.rows}x{grid.cols} cells, ~{grid.cell_m:.0f} m per cell", "cell_m": round(grid.cell_m, 1)},
            "scene": {"ids": [u["id"] for u in used], "date": when, "cloud_cover_pct": round(float(np.mean([u["properties"].get("eo:cloud_cover", np.nan) for u in used])), 1),
                      "native_resolution_m": 10, "analysis_cell_m": round(grid.cell_m, 1)},
            "ndvi": greenness_report(arr, inside, grid)}
        wc = _worldcover(grid)
        tree = None
        if wc is not None:
            try:
                out["land_cover"] = {**landcover_report(wc, inside, grid), "source": "ESA WorldCover 2021 v200, 10 m", "year": 2021}
                tree = np.isin(np.where(np.isfinite(wc), wc, 0).astype(int), FOREST)
            except ValueError:
                wc = None
        if wc is None:
            out["forest_note"] = "No valid forest classification was available for this region, so forest cover is not reported. Vegetation indicators below come from NDVI only."
        try:  # same-season comparison one year earlier, on the same grid
            d0 = datetime.fromisoformat(when)
            prev = _composite(_scenes(bbox, f"{(d0 - timedelta(days=410)).date()}/{(d0 - timedelta(days=320)).date()}", 40, 10), grid, inside)
            if prev:
                ch = change_report(arr, prev[0], inside, tree)
                if ch:
                    ch.update({"previous_scene_date": prev[1][0]["properties"]["datetime"][:10], "note": "Same season, one year earlier. Declines can reflect drought, harvest or fire as well as clearing; not confirmed deforestation."})
                    out["change"] = ch
        except Exception:  # noqa: BLE001 - optional
            pass
        stops = [(-0.1, (120, 90, 60)), (0.15, (214, 190, 110)), (0.35, (160, 200, 90)), (0.6, (60, 160, 70)), (0.9, (10, 90, 40))]
        ndvi_rgba = colorize(np.where(inside, arr["ndvi"], np.nan), stops, alpha=200)
        out["_overlays"] = [_class_overlay(wc, arr, inside, bbox),
                            overlay("ndvi", f"NDVI ({when})", ndvi_rgba, bbox, [{"color": "#785a3c", "label": "<0.1"}, {"color": "#a0c85a", "label": "0.35"}, {"color": "#0a5a28", "label": ">0.8"}], "Sentinel-2 L2A, clouds transparent")]
        out["source"] = "Sentinel-2 L2A (Earth Search STAC / AWS open data)" + ("; ESA WorldCover 2021" if wc is not None else "")
        return out
    import json as _json
    return cached(("veg2", key_bbox(bbox), hash(_json.dumps(geometry, sort_keys=True)) if geometry else 0), 12 * 3600, run)
