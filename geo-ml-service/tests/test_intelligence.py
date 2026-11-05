"""Processing tests: real raster files (UTM + WGS84 GeoTIFFs) through the full pipeline, provider-response handling, PDF content."""
import json
import subprocess
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

from app.api.routes.report import ReportRequest, build_pdf
from app.ingestion import geodata
from app.intelligence import satellite as sat
from app.intelligence import suitability as suit
from app.intelligence.climate import summarize
from app.intelligence.raster_io import Grid
from app.intelligence.terrain import analyze_dem
from app.prospectivity.auto import run_auto

BBOX = [77.30, 23.20, 77.36, 23.25]


# ------------------------------------------------------------------ rasters
def _write_scene(path, lon_split, cloud_rows=0, ndvi_forest=0.8, ndvi_other=0.25):
    """Sentinel-2-like UTM 43N GeoTIFFs (10 m): west of lon_split = dense vegetation, east = sparse."""
    tr = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    x0, y0 = tr.transform(77.27, 23.28)
    n = 1000
    xs = x0 + np.arange(n) * 10.0
    lon_of_col = tr.transform(xs, np.full(n, 23.22), direction="INVERSE")[0]
    west = np.tile(lon_of_col < lon_split, (n, 1))
    nir_refl = 0.4
    out = {}
    for name in ("red", "nir", "green", "scl"):
        arr = np.zeros((n, n), np.uint16)
        for veg, nd in ((west, ndvi_forest), (~west, ndvi_other)):
            red = nir_refl * (1 - nd) / (1 + nd)
            val = {"red": red, "nir": nir_refl, "green": 0.08}.get(name)
            if val is not None:
                arr[veg] = int(round(val * 10000)) + 1000 if name != "red" else (np.round(red * 10000) + 1000).astype(np.uint16)
        if name == "scl":
            arr[:] = 4
            arr[:cloud_rows, :] = 9
        p = path / f"{name}.tif"
        with rasterio.open(p, "w", driver="GTiff", height=n, width=n, count=1, dtype="uint16", crs="EPSG:32643", transform=from_origin(x0, y0, 10, 10), nodata=0) as d:
            d.write(arr, 1)
        out[name] = {"href": str(p), "raster:bands": [{"scale": 0.0001, "offset": -0.1 if name != "scl" else 0.0}] if name != "scl" else [{}]}
    return out


def _write_worldcover(path, lon_forest_max):
    n = 800
    tf = from_bounds(77.26, 23.16, 77.40, 23.30, n, n)
    cols = np.linspace(77.26, 77.40, n)
    arr = np.full((n, n), 40, np.uint8)             # cropland
    arr[:, cols < lon_forest_max] = 10               # forest west of the split
    arr[: n // 10, :] = 50                           # built-up strip at the north edge
    p = path / "wc.tif"
    with rasterio.open(p, "w", driver="GTiff", height=n, width=n, count=1, dtype="uint8", crs="EPSG:4326", transform=tf, nodata=0) as d:
        d.write(arr, 1)
    return str(p)


@pytest.fixture
def stac(tmp_path, monkeypatch):
    now = tmp_path / "now"; prev = tmp_path / "prev"; now.mkdir(); prev.mkdir()
    cur = _write_scene(now, 77.33, cloud_rows=600)
    old = _write_scene(prev, 77.33, ndvi_forest=0.55)    # forest was less green a year ago -> improved
    wc = _write_worldcover(tmp_path, 77.33)
    geom = {"type": "Polygon", "coordinates": [[[77.20, 23.10], [77.50, 23.10], [77.50, 23.40], [77.20, 23.40], [77.20, 23.10]]]}
    today = date.today()

    def fake(collection, bbox, datetime=None, limit=12, query=None, sort_desc=True):
        if collection == "esa-worldcover":
            return [{"id": "wc", "geometry": geom, "properties": {"datetime": "2021-06-01T00:00:00Z"}, "assets": {"map": {"href": wc}}}]
        start = date.fromisoformat(datetime.split("/")[0])
        recent = start > today - timedelta(days=200)
        d = today - timedelta(days=20) if recent else today - timedelta(days=365 + 15)
        return [{"id": "S2_NOW" if recent else "S2_PREV", "geometry": geom, "properties": {"datetime": d.isoformat() + "T05:30:00Z", "eo:cloud_cover": 5.0, "s2:processing_baseline": "05.11"}, "assets": cur if recent else old}]
    monkeypatch.setattr(sat, "stac_search", fake)
    sat._store = None
    from app.intelligence import common
    common._store.clear()
    return geom


def test_grid_area_matches_geodesic():
    g = Grid(BBOX)
    assert abs(g.rows * g.cols * g.cell_km2 - sat.region_area_km2(BBOX, None)) / sat.region_area_km2(BBOX, None) < 0.01


def test_vegetation_pipeline_real_rasters(stac):
    res = sat.vegetation(BBOX)
    lc, nd = res["land_cover"], res["ndvi"]
    # truth: forest = columns west of lon 77.33 inside lon 77.30-77.36 -> 50% (the built-up strip lies north of the bbox)
    assert abs(lc["forest"]["pct"] - 50.0) < 1.5
    assert abs(lc["forest"]["pct"] + lc["other_vegetation"]["pct"] + lc["non_vegetated"]["pct"] - 100) < 0.5
    assert lc["valid_classified_pct_of_region"] > 99
    # clouds: northern 600 rows (6 km from lat 23.28) mask ~48% of the region; reported separately
    assert 40 < nd["cloud_or_invalid_pct_of_region"] < 60
    assert nd["mean_ndvi"] > 0.3 and res["scene"]["analysis_cell_m"] > 0
    assert res["_overlays"][0]["id"] == "vegmap" and res["_overlays"][0]["image"].startswith("data:image/png")
    assert res["change"]["improved_pct"] > 20      # forest NDVI 0.55 -> 0.80 vs previous year (offset-corrected reflectance)


def test_polygon_mask_reduces_area(stac):
    half = {"type": "Polygon", "coordinates": [[[77.30, 23.20], [77.33, 23.20], [77.33, 23.25], [77.30, 23.25], [77.30, 23.20]]]}
    full = sat.vegetation(BBOX); sub = sat.vegetation(BBOX, half)
    assert 0.4 < sub["region"]["area_km2"] / full["region"]["area_km2"] < 0.6
    assert sub["land_cover"]["forest"]["pct"] > 90


def test_forest_not_reported_without_classification(stac, monkeypatch):
    monkeypatch.setattr(sat, "_worldcover", lambda grid: None)
    from app.intelligence import common
    common._store.clear()
    res = sat.vegetation(BBOX)
    assert "land_cover" not in res and "not reported" in res["forest_note"]
    assert res["_overlays"][0]["label"].startswith("Vegetation map (not a forest map)")


def test_clouds_not_counted_as_non_vegetated():
    g = Grid(BBOX); ins = np.ones(g.shape, bool)
    red = np.full(g.shape, 0.08); nir = np.full(g.shape, 0.4); green = np.full(g.shape, 0.1); scl = np.full(g.shape, 4); scl[: g.rows // 2] = 9
    r = sat.greenness_report(sat.indices(red, nir, green, scl), ins, g)
    assert r["greenness"]["green_vegetation"]["pct"] == 100.0 and abs(r["cloud_or_invalid_pct_of_region"] - 50) < 1


def test_reflectance_offset():
    assert sat.reflectance(np.array([5000.0]), {}, {"s2:processing_baseline": "05.11"})[0] == pytest.approx(0.4)
    assert sat.reflectance(np.array([4000.0]), {}, {"s2:processing_baseline": "03.00"})[0] == pytest.approx(0.4)


def test_aspect_direction():
    y, x = np.mgrid[0:60, 0:60]
    assert analyze_dem((100 + 3.0 * x).astype(float), [77, 23, 77.02, 23.02])["aspect_share_pct"]["W"] == 100.0


# ------------------------------------------------------------------ providers
def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("resp,needle", [
    (httpx.Response(200, text="<html>error</html>", headers={"content-type": "text/html"}), "HTML/XML"),
    (httpx.Response(200, text=""), "empty"), (httpx.Response(200, text="{bad", headers={"content-type": "application/json"}), "malformed"),
    (httpx.Response(200, json={"error": {"code": 400, "message": "bad params"}}), "bad params"), (httpx.Response(404, text="x"), "HTTP 404"),
    (httpx.Response(429, headers={"retry-after": "0"}), "429")])
def test_strict_json_diagnostics(resp, needle):
    with pytest.raises(geodata.ProviderError, match=needle):
        geodata.strict_json(_client(lambda r: resp), "GET", "https://energy.usgs.gov/x", retries=1)


def test_mrds_falls_back_and_normalises(monkeypatch):
    def handler(req):
        if "MapServer" in str(req.url):
            return httpx.Response(200, text="<html>Service unavailable</html>", headers={"content-type": "text/html"})
        return httpx.Response(200, json={"features": [{"attributes": {"DEP_ID": "7", "SITE_NAME": "Test mine", "COMMOD1": "Bauxite", "DEV_STAT": "Past Producer"}, "geometry": {"x": 77.31, "y": 23.21}}]})
    monkeypatch.setattr(geodata, "http", lambda timeout=20.0: _client(handler))
    recs, trunc, used = geodata.fetch_mrds(BBOX)
    assert recs[0]["kind"] == "mine_record" and "Hosted" in used and not trunc


def test_macrostrat_scale_fallback(monkeypatch):
    seen = []
    def handler(req):
        sc = req.url.params["scale"]; seen.append(sc)
        rows = [{"map_id": 1, "name": "Deccan Traps", "lith": "basalt", "b_int_name": "Cretaceous"}] if sc == "tiny" else []
        return httpx.Response(200, json={"success": {"data": rows}})
    monkeypatch.setattr(geodata, "http", lambda timeout=20.0: _client(handler))
    from app.intelligence import common
    common._store.clear()
    r = geodata.fetch_units(BBOX, None, n=3)
    assert r["scale"] == "tiny" and r["with_units"] == 9 and seen[:3] == ["large", "medium", "small"]


def test_run_auto_hides_unsupported():
    none_units = lambda b, g=None: {"units_per_point": [None] * 9, "points": 9, "answered": 0, "with_units": 0, "coverage": 0, "notes": ["down"], "scale": None, "source": "Macrostrat"}
    none_occ = lambda b: {"records": [], "providers": [{"name": "USGS MRDS", "ok": False, "detail": "HTTP 503"}], "available": False}
    r = run_auto(BBOX, None, None, none_units, none_occ)
    assert r["results"] == [] and r["geology"] is None and r["occurrences"] is None


def test_run_auto_scores_only_with_evidence():
    U = lambda **k: k
    units = lambda b, g=None: {"units_per_point": [[U(map_id=1, name="Deccan Traps", lith="basalt, laterite", _scale="small")], [U(map_id=2, name="Vindhyan", lith="limestone, shale, sandstone", _scale="small")]] * 8, "points": 16, "answered": 16, "with_units": 16, "coverage": 1.0, "notes": [], "scale": "small", "source": "Macrostrat"}
    f = lambda c, x, y, k="Past Producer": {"id": c + str(x), "name": "Mine " + c, "commodities": [c], "status": k, "kind": "mine_record", "lon": x, "lat": y, "source": "USGS MRDS", "verified": False}
    occ = lambda b: {"records": [f("Bauxite", 77.31, 23.21), f("Limestone", 77.32, 23.22)], "providers": [{"name": "USGS MRDS", "ok": True, "records": 2}], "available": True, "truncated": False}
    r = run_auto(BBOX, None, None, units, occ)
    names = {x["commodity"] for x in r["results"] if x["kind"] == "mineral"}
    assert names == {"bauxite", "limestone"} and all(x["potential_score"] is not None for x in r["results"])
    assert {x["commodity"] for x in r["occurrences"]["by_commodity"]} == {"bauxite", "limestone"}
    assert r["geology"]["composition"]


# ------------------------------------------------------------------ climate / suitability / pdf
def _climate():
    ts = [date(2015, 1, 1) + timedelta(days=i) for i in range(3652)]
    doy = np.array([t.timetuple().tm_yday for t in ts])
    return summarize({"time": [t.isoformat() for t in ts], "temperature_2m_mean": (25 + 8 * np.sin((doy - 100) / 365 * 6.283)).tolist(), "precipitation_sum": np.where((doy > 170) & (doy < 270), 9.0, 0.3).tolist(),
                      "et0_fao_evapotranspiration": [4.5] * 3652, "wind_speed_10m_max": [15.0] * 3652, "wind_direction_10m_dominant": [225.0] * 3652, "relative_humidity_2m_mean": [60.0] * 3652})


def test_suitability_withholds_without_data():
    assert suit.habitability(None, None, None, None, None)["status"] == "withheld"


def test_pdf_contains_results(stac, tmp_path):
    veg = sat.vegetation(BBOX); ov = [veg["_overlays"][0]]; veg.pop("_overlays")
    c = _climate()
    pr = {"geology": {"composition": [{"lithology": "Basalt / volcanic", "pct": 60.0}], "units": [{"name": "Deccan Traps", "lithology": "basalt", "age": "Cretaceous"}], "map_scale_note": "global small-scale map"},
          "occurrences": {"by_commodity": [{"commodity": "bauxite", "in_region": 1, "nearby": 2, "occurrences_prospects": 1, "mine_or_deposit_records": 2}], "records": [{"name": "Test mine", "commodities": ["Bauxite"], "kind": "mine_record", "status": "Past Producer", "in_region": True, "distance_km": 3}], "caveat": "Not a viable deposit."},
          "results": [], "limitations": ["coarse"], "sources": [{"name": "USGS MRDS", "available": True}, {"name": "Macrostrat", "available": False}], "disclaimer": "d"}
    pdf = build_pdf(ReportRequest(region={"name": "Bhopal test", "bbox": BBOX}, modules={"climate": c, "vegetation": veg}, overlays=ov, prospectivity=pr))
    p = tmp_path / "r.pdf"; p.write_bytes(pdf)
    text = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
    for needle in ("Forest cover", "Valid cloud-free data", "Region area", "Test mine", "Insufficient"[:0] or "Recorded occurrences"):
        assert needle in text
    assert "Insufficient evidence" not in text and "n/a" not in text.split("Region area")[1][:200]
