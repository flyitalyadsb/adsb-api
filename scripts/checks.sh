#!/bin/sh
# Offline checks, run by CI on every push and by the sync workflow before it commits.
# Needs python3 (3.8+), node (18+) and shellcheck.
set -eu
cd "$(dirname "$0")/.."

echo "== Python examples and scripts compile"
python3 -m py_compile examples/python/*.py scripts/*.py

echo "== sync.py: parses today's layouts, refuses what it can't parse"
python3 scripts/test_sync.py

echo "== Node example parses"
node --check examples/node/near.mjs

echo "== Shell example passes shellcheck"
shellcheck examples/curl.sh scripts/checks.sh

echo "== OpenAPI copy is valid JSON and OpenAPI 3"
python3 -c "import json,sys; d=json.load(open('openapi/openapi.json')); sys.exit(0 if str(d['openapi']).startswith('3.') and d['paths'] else 'not an OpenAPI 3 spec')"

echo "All checks passed."
