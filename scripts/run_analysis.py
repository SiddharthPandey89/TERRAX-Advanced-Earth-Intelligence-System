"""Run the supported point-weather analysis through the local Express API."""
from __future__ import annotations
import argparse
import json
import sys
import urllib.error
import urllib.request

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="User-facing place or analysis label")
    parser.add_argument("--latitude", required=True, type=float)
    parser.add_argument("--longitude", required=True, type=float)
    parser.add_argument("--api", default="http://127.0.0.1:5000/api/analysis")
    args = parser.parse_args()
    if not -90 <= args.latitude <= 90 or not -180 <= args.longitude <= 180:
        parser.error("latitude must be [-90,90] and longitude [-180,180]")
    payload = json.dumps({"regionName": args.name, "latitude": args.latitude, "longitude": args.longitude}).encode()
    request = urllib.request.Request(args.api, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as exc:
        print(exc.read(2048).decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Analysis API unavailable: {type(exc).__name__}", file=sys.stderr)
        return 1

if __name__ == "__main__": raise SystemExit(main())
