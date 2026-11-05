"""Offline integration tests for FastAPI routes; no live providers or database are contacted."""
from __future__ import annotations
import io
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
import rasterio
from rasterio.transform import from_origin
from rasterio.io import MemoryFile
from main import app
from app.api.routes.indicators import ProviderReading, RegionInput
from app.indicators.open_meteo import OpenMeteoIndicatorProvider
from app.indicators.usgs_elevation import USGSElevationIndicatorProvider
from app.ingestion.registry import IngestionResult
from app.ingestion.usgs.elevation import USGSElevationClient

POLYGON = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}

class GeoIntelligenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_registered_routes_and_catalog(self):
        response = self.client.get("/indicators/catalog")
        self.assertEqual(response.status_code, 200)
        data = {entry["name"]: entry for entry in response.json()["indicators"]}
        self.assertTrue(data["temperature"]["available"])
        self.assertTrue(data["rainfall"]["available"])
        self.assertTrue(data["elevation"]["available"])
        self.assertFalse(data["water_availability"]["available"])
        self.assertEqual(self.client.get("/ingestion/providers").status_code, 200)

    def test_indicator_uses_registered_provider_response(self):
        reading = ProviderReading(value=18.5, unit="°C", source="test provider", details={"classification": "provider_current_model_weather_value", "spatial_support": "single representative point; not an area average"})
        with patch.object(OpenMeteoIndicatorProvider, "fetch", new=AsyncMock(return_value=reading)):
            response = self.client.post("/indicators/analyze", json={"region": {"bbox": [10,10.01,10.02,10.03]}, "indicators": ["temperature", "water_availability"]})
        self.assertEqual(response.status_code, 200)
        data = {entry["indicator"]: entry for entry in response.json()["results"]}
        self.assertEqual(data["temperature"]["status"], "available")
        self.assertEqual(data["temperature"]["value"], 18.5)
        self.assertIn("not an area average", data["temperature"]["details"]["spatial_support"])
        self.assertEqual(data["water_availability"]["status"], "unavailable")
        self.assertIsNone(data["water_availability"]["value"])

    def test_usgs_accepts_numeric_string_and_preserves_point_provenance(self):
        payload = {"value": "4.169617176", "rasterId": 72150}
        with patch("app.ingestion.usgs.elevation.request_json", return_value=(payload, "https://example.test/epqs")):
            result = USGSElevationClient().query_point(37.8, -122.4)
        self.assertEqual(result.records[0]["elevation"], 4.169617176)
        self.assertEqual(result.records[0]["source_raster"], 72150)

        source_result = IngestionResult("usgs-elevation", "elevation-point", ({"elevation": 4.169617176, "unit": "Meters", "source_raster": 72150},), "https://example.test/epqs")
        with patch.object(USGSElevationClient, "query_point", return_value=source_result):
            reading = asyncio.run(USGSElevationIndicatorProvider().fetch(RegionInput(bbox=[-122.45, 37.75, -122.35, 37.85]), None))
        self.assertEqual(reading.value, 4.169617176)
        self.assertIn("not an area average", reading.details["spatial_support"])
        self.assertEqual(reading.details["source_product"], 72150)

    def test_patterns_derive_trend_from_supplied_values(self):
        response = self.client.post("/patterns/analyze", json={"method": "trend", "values": [2, 4, 6, 8], "source": "caller dataset", "unit": "mm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["direction"], "increasing")
        self.assertEqual(response.json()["classification"], "derived_model_output_from_caller_supplied_series")

    def test_habitability_withholds_score_without_required_evidence(self):
        response = self.client.post("/habitability/analyze", json={"region": {"point": {"latitude": 10, "longitude": 20}}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assessment"]["status"], "insufficient_data")
        self.assertIsNone(response.json()["assessment"]["score"])

    def test_prospectivity_marks_empty_evidence_as_unconfirmed_and_insufficient(self):
        response = self.client.post("/prospectivity/analyze", json={"region": {"point": {"latitude": 10, "longitude": 20}}, "targets": [{"kind": "mineral", "commodity": "gold", "evidence": []}]})
        self.assertEqual(response.status_code, 200)
        report = response.json()["report"]
        self.assertEqual(report["resource_status"], "unconfirmed_potential")
        self.assertEqual(report["results"][0]["status"], "insufficient_data")
        self.assertFalse(response.json()["discovery_claim"])

    def _geotiff(self) -> bytes:
        output = io.BytesIO()
        with MemoryFile() as memory:
            with memory.open(driver="GTiff", width=4, height=3, count=1, dtype="uint8", crs="EPSG:4326", transform=from_origin(0, 3, 1, 1)) as dataset:
                dataset.write(np.arange(12, dtype=np.uint8).reshape(3, 4), 1)
            output.write(memory.read())
        return output.getvalue()

    def test_raster_upload_inspect_and_quality(self):
        content = self._geotiff()
        inspect = self.client.post("/preprocessing/raster/inspect", files={"file": ("grid.tif", content, "image/tiff")})
        self.assertEqual(inspect.status_code, 200, inspect.text)
        self.assertEqual(inspect.json()["metadata"]["width"], 4)
        quality = self.client.post("/preprocessing/raster/quality", files={"file": ("grid.tif", content, "image/tiff")})
        self.assertEqual(quality.status_code, 200, quality.text)
        self.assertEqual(quality.json()["quality"]["valid_pixels"], 12)

    def test_reprojection_returns_a_file_and_cleans_after_response(self):
        content = self._geotiff()
        response = self.client.post("/preprocessing/raster/reproject", data={"target_crs": "EPSG:3857"}, files={"file": ("grid.tif", content, "image/tiff")})
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(response.headers["content-type"], "image/tiff")
        self.assertGreater(len(response.content), 100)

    def test_vector_validation_and_invalid_file_format(self):
        response = self.client.post("/preprocessing/vector/validate", json={"geometry": POLYGON})
        self.assertEqual(response.status_code, 200, response.text)
        invalid = self.client.post("/preprocessing/raster/inspect", files={"file": ("sample.txt", b"ignored", "text/plain")})
        self.assertEqual(invalid.status_code, 415)

    def test_api_does_not_expose_filesystem_path_upload_contract(self):
        response = self.client.post("/preprocessing/raster/inspect", json={"path": "C:/Users/me/private.tif"})
        self.assertEqual(response.status_code, 422)

if __name__ == "__main__": unittest.main()
