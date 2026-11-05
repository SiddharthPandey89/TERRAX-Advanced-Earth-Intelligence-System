"""Bounded upload-based geospatial preprocessing API.

The API never accepts caller-chosen server paths. Inputs and outputs live in a
request-specific temporary directory, have strict size/pixel budgets, and are
removed after JSON completion or after the generated file is streamed back.
"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.preprocessing.raster import RasterProcessingError, inspect_raster, validate_raster
from app.preprocessing.quality import assess_raster_quality
from app.preprocessing.reprojection import reproject_raster
from app.preprocessing.clipping import clip_raster
from app.preprocessing.masking import mask_raster
from app.preprocessing.vector import VectorProcessingError, coerce_geometry, geometry_bounds, reproject_geometry
from app.api.schemas.region import GeoJSONGeometry

router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 50_000_000
ALLOWED_RASTER = {".tif", ".tiff"}

class VectorValidationRequest(BaseModel):
    geometry: GeoJSONGeometry
    source_crs: str = "EPSG:4326"
    target_crs: str = "EPSG:4326"

async def _save_raster(upload: UploadFile, directory: Path) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_RASTER:
        raise HTTPException(415, "Only GeoTIFF (.tif, .tiff) uploads are supported by raster endpoints.")
    source = directory / ("source" + suffix)
    size = 0
    try:
        with source.open("wb") as target:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk: break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES: raise HTTPException(413, "Upload exceeds the 50 MiB limit.")
                target.write(chunk)
    finally:
        await upload.close()
    if size == 0: raise HTTPException(400, "Uploaded file is empty.")
    info = validate_raster(source)
    if info.width * info.height * info.count > MAX_PIXELS: raise HTTPException(413, "Raster exceeds the 50 million band-sample processing limit.")
    return source


def _info(info: Any) -> dict[str, Any]:
    return {"width": info.width, "height": info.height, "band_count": info.count,
            "dtypes": list(info.dtypes), "crs": info.crs, "bounds": list(info.bounds),
            "nodata": info.nodata, "pixel_count": info.width * info.height}


def _json_geometry(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > 1_000_000: raise HTTPException(413, "Geometry exceeds the 1 MiB limit.")
    try:
        value = json.loads(raw)
        validated = GeoJSONGeometry.model_validate(value)
        value = validated.model_dump()
        geometry = coerce_geometry(value)
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}: raise ValueError("Only Polygon and MultiPolygon geometries are accepted.")
        if len(geometry.wkt) > 1_000_000: raise ValueError("Geometry is too large.")
        bounds = geometry.bounds
        if not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90): raise ValueError("GeoJSON coordinates must be WGS84 longitude/latitude.")
        return dict(value.get("geometry") if value.get("type") == "Feature" else value)
    except (json.JSONDecodeError, TypeError, ValueError, VectorProcessingError) as exc:
        raise HTTPException(422, "Invalid Polygon or MultiPolygon GeoJSON geometry.") from exc


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RasterProcessingError): return HTTPException(422, "Raster operation failed; check the CRS, input geometry, nodata value, and supported file format.")
    return HTTPException(422, "The uploaded geospatial input could not be processed.")

@router.post("/raster/inspect")
async def raster_inspect(file: UploadFile = File(...)) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="earth_geo_") as tmp:
        try:
            source = await _save_raster(file, Path(tmp))
            return {"success": True, "metadata": _info(inspect_raster(source))}
        except HTTPException: raise
        except Exception as exc: raise _map_error(exc) from exc

@router.post("/raster/quality")
async def raster_quality(file: UploadFile = File(...)) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="earth_geo_") as tmp:
        try:
            source = await _save_raster(file, Path(tmp))
            report = assess_raster_quality(source)
            data = {"width": report.width, "height": report.height, "band_count": report.band_count,
                    "crs": report.crs, "total_pixels": report.total_pixels, "valid_pixels": report.valid_pixels,
                    "valid_pixel_fraction": report.valid_pixel_fraction, "issues": list(report.issues), "is_valid": report.is_valid}
            return {"success": True, "quality": data}
        except HTTPException: raise
        except Exception as exc: raise _map_error(exc) from exc

async def _file_result(file: UploadFile, operation: str, parameters: dict[str, Any], background_tasks: BackgroundTasks) -> FileResponse:
    tmp = Path(tempfile.mkdtemp(prefix="earth_geo_"))
    try:
        source = await _save_raster(file, tmp)
        output = tmp / f"processed_{operation}.tif"
        if operation == "reproject":
            info = reproject_raster(source, output, parameters["target_crs"], resampling=parameters["resampling"])
        elif operation == "clip":
            info = clip_raster(source, output, parameters["geometry"], geometry_crs=parameters["geometry_crs"])
        else:
            info = mask_raster(source, output, geometry=parameters.get("geometry"), geometry_crs=parameters["geometry_crs"], valid_min=parameters.get("valid_min"), valid_max=parameters.get("valid_max"))
        if info.width * info.height * info.count > MAX_PIXELS: raise HTTPException(413, "Processed raster exceeds the 50 million band-sample limit.")
        background_tasks.add_task(shutil.rmtree, tmp, True)
        return FileResponse(path=output, media_type="image/tiff", filename=f"{operation}.tif", background=background_tasks)
    except HTTPException:
        shutil.rmtree(tmp, ignore_errors=True); raise
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True); raise _map_error(exc) from exc

@router.post("/raster/reproject")
async def raster_reproject(background_tasks: BackgroundTasks, file: UploadFile = File(...), target_crs: str = Form(...), resampling: str = Form("nearest")) -> FileResponse:
    if len(target_crs) > 100: raise HTTPException(422, "target_crs is too long.")
    return await _file_result(file, "reproject", {"target_crs": target_crs, "resampling": resampling}, background_tasks)

@router.post("/raster/clip")
async def raster_clip(background_tasks: BackgroundTasks, file: UploadFile = File(...), geometry: str = Form(...), geometry_crs: str = Form("EPSG:4326")) -> FileResponse:
    return await _file_result(file, "clip", {"geometry": _json_geometry(geometry), "geometry_crs": geometry_crs}, background_tasks)

@router.post("/raster/mask")
async def raster_mask(background_tasks: BackgroundTasks, file: UploadFile = File(...), geometry: str | None = Form(default=None), valid_min: float | None = Form(default=None), valid_max: float | None = Form(default=None), geometry_crs: str = Form("EPSG:4326")) -> FileResponse:
    if valid_min is not None and not math.isfinite(valid_min) or valid_max is not None and not math.isfinite(valid_max): raise HTTPException(422, "Mask limits must be finite numbers.")
    shape = _json_geometry(geometry) if geometry else None
    if shape is None and valid_min is None and valid_max is None: raise HTTPException(422, "Provide geometry or at least one numeric validity bound.")
    return await _file_result(file, "mask", {"geometry": shape, "geometry_crs": geometry_crs, "valid_min": valid_min, "valid_max": valid_max}, background_tasks)

@router.post("/vector/validate")
async def validate_vector(payload: VectorValidationRequest) -> dict[str, Any]:
    try:
        parsed = coerce_geometry(payload.geometry.model_dump())
        projected = reproject_geometry(parsed, payload.source_crs, payload.target_crs)
        return {"success": True, "geometry_type": parsed.geom_type, "bounds": list(geometry_bounds(projected)), "source_crs": payload.source_crs, "target_crs": payload.target_crs}
    except (ValueError, VectorProcessingError) as exc: raise HTTPException(422, "Invalid vector geometry or CRS.") from exc
