"""Public geology and mineral-record clients with strict response validation.

Providers (all keyless):
* Macrostrat geologic map units (point queries; best available map scale is detected per region).
* USGS MRDS via the USGS ArcGIS REST services (primary) - recorded occurrences / prospects / mine records.
* USGS "Major mineral deposits of the world" (ArcGIS) - best effort.
* OpenStreetMap (Overpass) - mapped mining sites carrying a ``resource`` tag.

Every request validates HTTP status, content type and body; HTML/XML error pages, empty bodies,
rate limits and malformed JSON become a ProviderError with a short diagnostic, never an unhandled crash.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from app.intelligence.common import cached, http

ARCGIS_MRDS = [
    "https://energy.usgs.gov/arcgis/rest/services/MRData/Mineral_Resource_Data_System/MapServer/3",
    "https://energy.usgs.gov/arcgis/rest/services/Hosted/Mineral_Resource_Data_System/FeatureServer/0",
]
ARCGIS_MAJOR = "https://energy.usgs.gov/arcgis/rest/services/Hosted/Major_mineral_deposits/FeatureServer/0"
MACROSTRAT = "https://macrostrat.org/api/v2/geologic_units/map"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
SCALES = ("large", "medium", "small", "tiny")  # Macrostrat map scales, finest first; only "tiny" is global


class ProviderError(Exception):
    """A provider answered, but not with usable data. ``str(e)`` is a short diagnostic."""


def strict_json(client: httpx.Client, method: str, url: str, *, retries: int = 2, **kw: Any) -> Any:
    last = "no response"
    for attempt in range(retries + 1):
        try:
            r = client.request(method, url, **kw)
        except httpx.TransportError as exc:
            last = f"network error ({type(exc).__name__})"
            time.sleep(1.0 + attempt)
            continue
        ctype = r.headers.get("content-type", "")
        if r.status_code in (429, 502, 503, 504):
            last = f"HTTP {r.status_code} (rate limit/overload)"
            try:
                wait = min(8.0, float(r.headers.get("retry-after", 1.5 * (attempt + 1))))
            except ValueError:
                wait = 1.5 * (attempt + 1)
            if attempt < retries:
                time.sleep(wait)
            continue
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code} from {httpx.URL(url).host} ({ctype or 'no content-type'})")
        body = r.text.strip()
        if not body:
            raise ProviderError(f"empty response from {httpx.URL(url).host}")
        if body[:1] == "<":
            raise ProviderError(f"{httpx.URL(url).host} returned HTML/XML, not JSON (content-type {ctype or 'none'}): {body[:80]!r}")
        try:
            data = json.loads(body)
        except ValueError:
            raise ProviderError(f"{httpx.URL(url).host} returned malformed JSON (content-type {ctype or 'none'}): {body[:80]!r}") from None
        if isinstance(data, dict) and isinstance(data.get("error"), (dict, str)):
            err = data["error"]
            raise ProviderError(f"{httpx.URL(url).host} error: {(err.get('message') if isinstance(err, dict) else err)!s:.100}")
        return data
    raise ProviderError(f"{httpx.URL(url).host}: {last}")


# ---------------------------------------------------------------- Macrostrat
def grid_points(bbox: list[float], n: int, geometry: dict | None = None) -> list[tuple[float, float]]:
    """(lon, lat) cell-centre points; with a polygon, only points inside it (uniform sampling = area-proportional)."""
    west, south, east, north = bbox
    pts = [(west + (i + 0.5) * (east - west) / n, south + (j + 0.5) * (north - south) / n) for j in range(n) for i in range(n)]
    if geometry:
        try:
            from shapely.geometry import Point, shape
            poly = shape(geometry)
            inside = [p for p in pts if poly.contains(Point(p))]
            pts = inside or [(poly.representative_point().x, poly.representative_point().y)]
        except Exception:  # noqa: BLE001
            pass
    return pts


def _macro_point(client: httpx.Client, base: str, lon: float, lat: float, scale: str) -> list[dict[str, Any]]:
    data = strict_json(client, "GET", base, retries=1, params={"lat": round(lat, 5), "lng": round(lon, 5), "scale": scale, "response": "long", "format": "json"})
    rows = ((data.get("success") or {}).get("data")) if isinstance(data, dict) else None
    if rows is None:
        raise ProviderError("Macrostrat response had no success.data")
    return [u for u in rows if isinstance(u, dict)]


def fetch_units(bbox: list[float], geometry: dict | None = None, n: int = 6) -> dict[str, Any]:
    """Sample Macrostrat map units on an n x n grid inside the region, at the finest map scale that has coverage."""
    base = os.getenv("MACROSTRAT_API_URL", MACROSTRAT).strip() or MACROSTRAT
    pts = grid_points(bbox, n, geometry)
    notes: list[str] = []
    centre = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    probe = pts[len(pts) // 2] if geometry else centre
    scale_used, failures = None, 0
    with http(20) as c:
        for sc in SCALES:  # detect the finest scale that actually has a map here
            try:
                if _macro_point(c, base, *probe, sc):
                    scale_used = sc; break
            except ProviderError as exc:
                failures += 1; last = str(exc)
        if scale_used is None:
            notes.append("Macrostrat returned no mapped geologic unit at any scale for the region centre." if failures < len(SCALES) else f"Macrostrat unavailable: {last}")
            return {"units_per_point": [None] * len(pts), "points": len(pts), "answered": 0 if failures == len(SCALES) else len(pts), "with_units": 0, "coverage": 0.0, "scale": None, "notes": notes, "source": "Macrostrat"}

        coarser = SCALES[SCALES.index(scale_used):]

        def one(pt: tuple[float, float]) -> list[dict[str, Any]] | None:
            def run() -> list[dict[str, Any]] | None:
                ans = False
                for sc in coarser:
                    try:
                        rows = _macro_point(c, base, pt[0], pt[1], sc); ans = True
                    except ProviderError:
                        continue
                    if rows:
                        for r in rows:
                            r["_scale"] = sc
                        return rows
                return [] if ans else None
            return cached(("macro", round(pt[0], 4), round(pt[1], 4), scale_used), 24 * 3600, run)
        with ThreadPoolExecutor(max_workers=8) as pool:
            res = list(pool.map(one, pts))
    answered = [r for r in res if r is not None]
    with_units = [r for r in answered if r]
    if len(answered) < len(pts):
        notes.append(f"{len(pts) - len(answered)} of {len(pts)} sample points could not be queried.")
    return {"units_per_point": res, "points": len(pts), "answered": len(answered), "with_units": len(with_units), "coverage": len(with_units) / len(pts) if pts else 0.0,
            "scale": scale_used, "notes": notes, "source": f"Macrostrat geologic map units ({scale_used}-scale maps)"}


# ---------------------------------------------------------------- mineral records
def _lc(d: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in d.items()}


def _kind(dev: str | None) -> str:
    d = (dev or "").lower()
    if "past" in d or "producer" in d:
        return "mine_record"
    if "prospect" in d:
        return "prospect"
    if "plant" in d:
        return "plant"
    return "occurrence"


def _arcgis_query(client: httpx.Client, layer: str, box: list[float]) -> tuple[list[dict[str, Any]], bool]:
    data = strict_json(client, "GET", f"{layer}/query", params={
        "where": "1=1", "geometry": ",".join(f"{v:.5f}" for v in box), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "outSR": 4326, "resultRecordCount": 2000, "f": "json"})
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        raise ProviderError("ArcGIS response had no features array")
    return feats, bool(data.get("exceededTransferLimit"))


def _normalise_mrds(f: dict[str, Any], source: str) -> dict[str, Any] | None:
    a = _lc(f.get("attributes") or {})
    g = f.get("geometry") or {}
    lon = g.get("x", a.get("longitude")); lat = g.get("y", a.get("latitude"))
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    comm = [str(a[k]).strip() for k in ("commod1", "commod2", "commod3") if a.get(k)]
    comm = [x for part in comm for x in part.replace(";", ",").split(",") if x.strip()]
    return {"id": str(a.get("dep_id") or a.get("objectid") or ""), "name": str(a.get("site_name") or a.get("dep_name") or "unnamed site").strip(), "commodities": [c.strip() for c in comm],
            "status": a.get("dev_stat"), "kind": _kind(a.get("dev_stat")), "deposit_type": a.get("dep_type"), "size": a.get("prod_size"), "lon": lon, "lat": lat, "source": source, "verified": False}


def fetch_mrds(box: list[float], depth: int = 0) -> tuple[list[dict[str, Any]], bool, str]:
    """MRDS records in ``box``; splits the box if the server truncates. Returns (records, truncated, provider_used)."""
    last = "no provider tried"
    with http(40) as c:
        for layer in ARCGIS_MRDS:
            try:
                feats, exceeded = _arcgis_query(c, layer, box)
            except ProviderError as exc:
                last = str(exc); continue
            if exceeded and depth < 2:
                w, s, e, n = box; mx, my = (w + e) / 2, (s + n) / 2
                recs: dict[str, dict[str, Any]] = {}; trunc = False
                for q in ([w, s, mx, my], [mx, s, e, my], [w, my, mx, n], [mx, my, e, n]):
                    rr, tt, _ = fetch_mrds(q, depth + 1)
                    trunc = trunc or tt
                    for r in rr:
                        recs[r["id"] or f"{r['lon']:.5f},{r['lat']:.5f},{r['name']}"] = r
                return list(recs.values()), trunc, layer.split("/services/")[1].split("/MapServer")[0].split("/FeatureServer")[0]
            recs_ = [r for r in (_normalise_mrds(f, "USGS MRDS") for f in feats) if r]
            return recs_, exceeded, layer.split("/services/")[1].split("/MapServer")[0].split("/FeatureServer")[0]
    raise ProviderError(last)


def fetch_major_deposits(box: list[float]) -> list[dict[str, Any]]:
    with http(30) as c:
        feats, _ = _arcgis_query(c, ARCGIS_MAJOR, box)
    out = []
    for f in feats:
        a = _lc(f.get("attributes") or {}); g = f.get("geometry") or {}
        try:
            lon, lat = float(g.get("x", a.get("longitude"))), float(g.get("y", a.get("latitude")))
        except (TypeError, ValueError):
            continue
        comm = [str(v) for k, v in a.items() if "commod" in k and v]
        out.append({"id": str(a.get("objectid") or ""), "name": str(a.get("dep_name") or "unnamed deposit"), "commodities": comm, "status": "listed major deposit", "kind": "major_deposit",
                    "lon": lon, "lat": lat, "source": "USGS Major mineral deposits of the world", "verified": False})
    return out


OSM_RES = {"iron_ore": "iron ore", "iron": "iron ore", "copper": "copper", "gold": "gold", "bauxite": "bauxite", "limestone": "limestone", "manganese": "manganese", "coal": "coal"}


def fetch_osm_mines(box: list[float]) -> list[dict[str, Any]]:
    if box[2] - box[0] > 3.5 or box[3] - box[1] > 3.5:
        raise ProviderError("region too large for OpenStreetMap mining-site query")
    b = f"({box[1]},{box[0]},{box[3]},{box[2]})"
    pat = "|".join(OSM_RES)
    q = f'[out:json][timeout:30];(nwr["resource"~"^({pat})$"]["landuse"~"quarry|industrial"]{b};nwr["resource"~"^({pat})$"]["industrial"="mine"]{b};nwr["resource"~"^({pat})$"]["man_made"~"mineshaft|adit"]{b};nwr["resource"~"^({pat})$"]["disused:landuse"="quarry"]{b};);out center tags 400;'
    last = "no mirror tried"
    for url in OVERPASS:
        try:
            with http(40) as c:
                data = strict_json(c, "POST", url, retries=1, data={"data": q})
        except ProviderError as exc:
            last = str(exc); continue
        out = []
        for el in data.get("elements", []):
            t = el.get("tags") or {}
            lon = el.get("lon", (el.get("center") or {}).get("lon")); lat = el.get("lat", (el.get("center") or {}).get("lat"))
            comm = [OSM_RES[x] for x in str(t.get("resource", "")).split(";") if x.strip() in OSM_RES]
            if lon is None or lat is None or not comm:
                continue
            out.append({"id": f"osm-{el.get('type')}-{el.get('id')}", "name": t.get("name") or t.get("operator") or "unnamed mining site", "commodities": comm, "status": "mapped site" + (" (disused)" if "disused:landuse" in t else ""),
                        "kind": "mapped_site", "lon": float(lon), "lat": float(lat), "source": "OpenStreetMap (volunteer-mapped)", "verified": False})
        return out
    raise ProviderError(last)


def fetch_occurrences(bbox: list[float], buffer_deg: float = 0.25) -> dict[str, Any]:
    """All recorded mineral information for the region + a small buffer, with per-provider diagnostics."""
    box = [max(-180.0, bbox[0] - buffer_deg), max(-90.0, bbox[1] - buffer_deg), min(180.0, bbox[2] + buffer_deg), min(90.0, bbox[3] + buffer_deg)]
    providers: list[dict[str, Any]] = []; records: list[dict[str, Any]] = []; truncated = False

    def run(name: str, fn):
        try:
            res = cached((name, tuple(round(v, 3) for v in box)), 6 * 3600, fn)
            providers.append({"name": name, "ok": True, "records": len(res[0] if isinstance(res, tuple) else res)})
            return res
        except ProviderError as exc:
            providers.append({"name": name, "ok": False, "detail": str(exc)[:200]})
        except Exception as exc:  # noqa: BLE001
            providers.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {str(exc)[:120]}"})
        return None
    mrds = run("USGS MRDS", lambda: fetch_mrds(box))
    if mrds:
        records += [r for r in mrds[0] if r["kind"] != "plant"]; truncated = mrds[1]
    major = run("USGS Major mineral deposits", lambda: fetch_major_deposits(box))
    if major:
        records += major
    osm = run("OpenStreetMap mining sites", lambda: fetch_osm_mines(box))
    if osm:
        records += osm
    return {"records": records, "providers": providers, "available": any(p["ok"] for p in providers), "truncated": truncated, "search_bbox": box}
