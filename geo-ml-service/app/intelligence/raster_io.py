"""STAC search (Earth Search, no credentials) and exact-grid raster reads.

Every layer (Sentinel-2, WorldCover, DEM) is warped onto ONE common WGS84 grid that
exactly covers the selected bounding box, so all layers align pixel-for-pixel and
the region area per cell is known.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from shapely.geometry import box, shape

from .common import http

STAC = "https://earth-search.aws.element84.com/v1/search"
MAX_PX = 512
GDAL = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff", GDAL_HTTP_MAX_RETRY="2",
            GDAL_HTTP_RETRY_DELAY="1", GDAL_HTTP_TIMEOUT="25", GDAL_HTTP_CONNECTTIMEOUT="8", AWS_NO_SIGN_REQUEST="YES", VSI_CACHE="TRUE")


class Grid:
    """Common analysis grid: WGS84 cells covering ``bbox`` exactly."""

    def __init__(self, bbox: list[float], max_px: int = MAX_PX, native_m: float = 10.0):
        w, s, e, n = bbox
        lat = (s + n) / 2
        self.bbox = bbox
        self.width_m = (e - w) * 111320.0 * math.cos(math.radians(lat))
        self.height_m = (n - s) * 110574.0
        longest = max(self.width_m, self.height_m)
        cells = int(min(max_px, max(8, math.ceil(longest / native_m))))
        scale = cells / longest
        self.cols = max(4, int(round(self.width_m * scale)))
        self.rows = max(4, int(round(self.height_m * scale)))
        self.dx_m = self.width_m / self.cols
        self.dy_m = self.height_m / self.rows
        self.cell_km2 = self.dx_m * self.dy_m / 1e6
        self.transform = from_bounds(w, s, e, n, self.cols, self.rows)
        self.shape = (self.rows, self.cols)

    @property
    def cell_m(self) -> float:
        return math.sqrt(self.dx_m * self.dy_m)

    def inside_mask(self, geometry: dict | None) -> np.ndarray:
        """True for cells inside the selected polygon (all True for a plain bounding box)."""
        if not geometry:
            return np.ones(self.shape, dtype=bool)
        m = ~geometry_mask([geometry], out_shape=self.shape, transform=self.transform, all_touched=False)
        return m if m.any() else np.ones(self.shape, dtype=bool)


def stac_search(collection: str, bbox: list[float], datetime: str | None = None, limit: int = 12, query: dict | None = None, sort_desc: bool = True) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"collections": [collection], "bbox": bbox, "limit": limit}
    if datetime:
        body["datetime"] = datetime
    if query:
        body["query"] = query
    if sort_desc:
        body["sortby"] = [{"field": "properties.datetime", "direction": "desc"}]
    with http(25) as c:
        r = c.post(STAC, json=body)
        r.raise_for_status()
        return r.json().get("features", [])


def coverage(item: dict[str, Any], bbox: list[float]) -> float:
    b = box(*bbox)
    return float(shape(item["geometry"]).intersection(b).area / b.area) if b.area else 0.0


def read_grid(href: str, grid: Grid, resampling: Resampling = Resampling.bilinear, nodata: float | None = None) -> np.ndarray:
    """Read one band warped onto ``grid``. Returns float64 with NaN where there is no data."""
    with rasterio.Env(**GDAL), rasterio.open(href) as src:
        nd = src.nodata if nodata is None else nodata
        with WarpedVRT(src, crs="EPSG:4326", transform=grid.transform, width=grid.cols, height=grid.rows, resampling=resampling,
                       src_nodata=nd, nodata=nd if nd is not None else None) as vrt:
            arr = vrt.read(1, masked=True)
    out = np.ma.filled(arr.astype("float64"), np.nan)
    if nd is not None:
        out[out == nd] = np.nan
    return out


def read_mosaic(hrefs: list[str], grid: Grid, resampling: Resampling = Resampling.nearest, nodata: float | None = None) -> np.ndarray | None:
    """Mosaic several tiles onto the grid; first tile with data wins. None if nothing covers the region."""
    out: np.ndarray | None = None
    for h in hrefs:
        arr = read_grid(h, grid, resampling, nodata)
        out = arr if out is None else np.where(np.isnan(out), arr, out)
        if out is not None and np.isfinite(out).all():
            break
    return out if out is not None and np.isfinite(out).any() else None
