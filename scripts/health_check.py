"""Check local HTTP service readiness without contacting external providers."""
from __future__ import annotations
import argparse
import sys
import urllib.error
import urllib.request

SERVICES = {"frontend": "http://127.0.0.1:5173/", "backend": "http://127.0.0.1:5000/api/health", "ml": "http://127.0.0.1:8000/health"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=["all", *SERVICES], default="all")
    args = parser.parse_args()
    selected = SERVICES.items() if args.service == "all" else [(args.service, SERVICES[args.service])]
    failed = False
    for name, url in selected:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                ok = 200 <= response.status < 400
                print(f"{'OK' if ok else 'FAIL'} {name}: HTTP {response.status}")
                failed |= not ok
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"FAIL {name}: {type(exc).__name__}; see README troubleshooting")
            failed = True
    return 1 if failed else 0

if __name__ == "__main__": raise SystemExit(main())
