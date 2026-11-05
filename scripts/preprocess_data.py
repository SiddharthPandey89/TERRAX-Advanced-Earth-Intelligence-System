"""Call the FastAPI upload-based raster preprocessing API for a local GeoTIFF."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import httpx

OPERATIONS = ("inspect", "quality", "reproject", "clip", "mask")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--operation", choices=OPERATIONS, default="inspect")
    parser.add_argument("--api", default="http://127.0.0.1:8000/preprocessing")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-crs")
    parser.add_argument("--geometry", type=Path, help="GeoJSON Polygon/MultiPolygon file for clip/mask")
    parser.add_argument("--valid-min", type=float)
    parser.add_argument("--valid-max", type=float)
    parser.add_argument("--resampling", default="nearest")
    args = parser.parse_args()
    if not args.file.is_file(): parser.error("input file does not exist")
    if args.file.stat().st_size > 50 * 1024 * 1024: parser.error("input exceeds the 50 MiB limit")
    fields = {}
    if args.operation == "reproject":
        if not args.target_crs: parser.error("--target-crs is required for reproject")
        fields.update(target_crs=args.target_crs, resampling=args.resampling)
    elif args.operation in {"clip", "mask"}:
        if args.geometry: fields["geometry"] = args.geometry.read_text(encoding="utf-8")
        if args.operation == "clip" and not args.geometry: parser.error("--geometry is required for clip")
        if args.operation == "mask" and args.valid_min is None and args.valid_max is None and not args.geometry: parser.error("mask needs --geometry or a numeric bound")
        if args.valid_min is not None: fields["valid_min"] = str(args.valid_min)
        if args.valid_max is not None: fields["valid_max"] = str(args.valid_max)
    url = f"{args.api.rstrip('/')}/raster/{args.operation}"
    try:
        with httpx.Client(timeout=120) as client, args.file.open("rb") as source:
            response = client.post(url, files={"file": (args.file.name, source, "image/tiff")}, data=fields)
        if not response.is_success:
            print(response.text[:2048], file=sys.stderr); return 1
        if args.operation in {"inspect", "quality"}:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False)); return 0
        output = args.output or args.file.with_name(f"{args.file.stem}_{args.operation}.tif")
        output.write_bytes(response.content)
        print(f"Saved processed raster: {output}")
        return 0
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"Preprocessing request failed ({type(exc).__name__}). Is the ML service running?", file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
