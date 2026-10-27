#!/usr/bin/env python3
"""Refresh only openapi/openapi.json from the spec the API publishes.

    python3 scripts/refresh_openapi.py          # rewrite the copy
    python3 scripts/refresh_openapi.py --check  # exit 1 if the copy is out of date

scripts/sync.py does this and more (plans, coverage, safety checks) and is what the
daily sync workflow runs; this script is the spec-only shortcut.
Python 3.8+, no dependencies.
"""

import sys

from sync import OPENAPI_PATH, SyncError, fetch_openapi


def main() -> None:
    try:
        _, fresh = fetch_openapi()
    except SyncError as e:
        sys.exit(str(e))
    current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
    if "--check" in sys.argv:
        if fresh != current:
            sys.exit(f"{OPENAPI_PATH.name} is out of date: run python3 scripts/sync.py")
        print(f"{OPENAPI_PATH.name} is up to date")
        return
    OPENAPI_PATH.write_text(fresh, encoding="utf-8")
    print(f"{OPENAPI_PATH.name}: {'updated' if fresh != current else 'unchanged'}")


if __name__ == "__main__":
    main()
