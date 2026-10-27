#!/usr/bin/env python3
"""Refresh openapi/openapi.json from the spec the API publishes.

    python3 scripts/refresh_openapi.py          # rewrite the copy
    python3 scripts/refresh_openapi.py --check  # exit 1 if the copy is out of date

The live spec at https://flyitalyadsb.com/openapi.json is the source of truth;
this copy is pretty-printed so changes show up as readable diffs.
Python 3.8+, no dependencies.
"""

import json
import pathlib
import sys
import urllib.request

SOURCE = "https://flyitalyadsb.com/openapi.json"
TARGET = pathlib.Path(__file__).resolve().parent.parent / "openapi" / "openapi.json"


def fetch() -> str:
    # A User-Agent of our own: the site refuses Python's default "Python-urllib/x.y".
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "flyitalyadsb-adsb-api-repo/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        spec = json.load(r)
    if not str(spec.get("openapi", "")).startswith("3."):
        sys.exit(f"{SOURCE} did not return an OpenAPI 3 document")
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    fresh = fetch()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    if "--check" in sys.argv:
        if fresh != current:
            sys.exit(f"{TARGET.name} is out of date: run python3 scripts/refresh_openapi.py")
        print(f"{TARGET.name} is up to date")
        return
    TARGET.write_text(fresh, encoding="utf-8")
    print(f"{TARGET.name}: {'updated' if fresh != current else 'unchanged'}")


if __name__ == "__main__":
    main()
