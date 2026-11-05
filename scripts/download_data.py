"""Discover provider catalog records through local APIs; this tool does not download rasters."""
from __future__ import annotations
import argparse
import json
import sys
import urllib.error
import urllib.request

PROVIDERS = ("nasa-modis", "copernicus-sentinel", "usgs-elevation", "usgs-geology", "openstreetmap")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=PROVIDERS)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--query", help="Required for OpenStreetMap place search")
    parser.add_argument("--product", default="MOD13Q1", choices=("MOD13Q1", "MOD11A1", "MCD12Q1"))
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--api", default="http://127.0.0.1:5000/api/ml")
    args = parser.parse_args()
    body = {"limit": 20}
    if args.bbox: body["bbox"] = args.bbox
    if args.query: body["query"] = args.query
    if args.product: body["product"] = args.product
    if args.start_date: body["start_date"] = args.start_date
    if args.end_date: body["end_date"] = args.end_date
    url = f"{args.api.rstrip('/')}/ingestion/{args.provider}/search"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=100) as response:
            print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
        print("\nCatalog discovery only; no raster or satellite asset was downloaded.", file=sys.stderr)
        return 0
    except urllib.error.HTTPError as exc:
        print(exc.read(2048).decode("utf-8", errors="replace"), file=sys.stderr); return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Provider query failed: {type(exc).__name__}", file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
