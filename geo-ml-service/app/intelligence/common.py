"""Shared helpers: TTL cache, HTTP client, PNG overlay encoder."""
from __future__ import annotations

import base64
import struct
import threading
import time
import zlib
from typing import Any, Callable

import httpx
import numpy as np

HEADERS = {"User-Agent": "earth-geointelligence-ml-service/0.2"}
_store: dict[Any, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached(key: Any, ttl: float, fn: Callable[[], Any]) -> Any:
    """Return a fresh cached value or compute it. Exceptions are never cached."""
    now = time.time()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _lock:
        _store[key] = (now, value)
        if len(_store) > 200:
            for k in sorted(_store, key=lambda k: _store[k][0])[:50]:
                _store.pop(k, None)
    return value


def key_bbox(bbox: list[float], nd: int = 3) -> tuple:
    return tuple(round(v, nd) for v in bbox)


def http(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=6.0), headers=HEADERS, follow_redirects=True)


def get_json(client: httpx.Client, url: str, retries: int = 1, **kw: Any) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = client.get(url, **kw)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.0)
    raise last  # type: ignore[misc]


def ok(v: Any) -> bool:
    return isinstance(v, (int, float, np.floating, np.integer)) and not isinstance(v, bool) and np.isfinite(v)


def png_data_url(rgba: np.ndarray) -> str:
    """Encode an (H, W, 4) uint8 array as a PNG data URL (no Pillow dependency)."""
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


def colorize(values: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]], valid: np.ndarray | None = None, alpha: int = 200) -> np.ndarray:
    xs = [s[0] for s in stops]
    out = np.zeros(values.shape + (4,), dtype=np.uint8)
    v = np.nan_to_num(values.astype("float64"), nan=xs[0])
    for c in range(3):
        out[..., c] = np.interp(v, xs, [s[1][c] for s in stops]).astype(np.uint8)
    mask = np.isfinite(values) if valid is None else (valid & np.isfinite(values))
    out[..., 3] = np.where(mask, alpha, 0)
    return out


def overlay(oid: str, label: str, rgba: np.ndarray, bbox: list[float], legend: list[dict[str, str]], note: str = "") -> dict[str, Any]:
    w, s, e, n = bbox
    return {"id": oid, "label": label, "image": png_data_url(rgba), "bounds": [[s, w], [n, e]], "legend": legend, "note": note}
