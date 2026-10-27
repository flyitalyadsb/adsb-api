#!/usr/bin/env python3
"""What flew over this place? The aircraft that passed within a few km of a point.

For noise complaints, helicopter logs and "what was that plane at 7 am?".

    export FLYITALYADSB_API_KEY=...
    python3 overflights.py 51.5007 -0.1246                   # last 2 hours, 5 km (Westminster)
    python3 overflights.py 40.7580 -73.9855 --hours 6 --max-alt 3000
    python3 overflights.py 45.46 9.19 --from 2026-10-26T06:00:00Z --to 2026-10-26T09:00:00Z

Covers every day since 2026-08-17 and today up to about 10 minutes ago.
The radius and time window allowed per request depend on the plan (see /v2/overflights in
openapi/openapi.json); the defaults here fit the Free plan.
Python 3.8+, standard library only.
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def main():
    parser = argparse.ArgumentParser(description="Aircraft that flew over a point.")
    parser.add_argument("lat", type=float)
    parser.add_argument("lon", type=float)
    parser.add_argument("--km", type=float, default=5, help="radius in km (default 5)")
    parser.add_argument("--hours", type=float, default=2, help="window ending now (default 2)")
    parser.add_argument("--from", dest="start", help="window start, ISO 8601 (UTC if no offset)")
    parser.add_argument("--to", dest="end", help="window end, ISO 8601")
    parser.add_argument("--max-alt", type=float, help="only the part of each track at or below this altitude, feet")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    params = {
        "lat": args.lat, "lon": args.lon, "dist": args.km,
        "from": args.start or (now - timedelta(hours=args.hours)).isoformat(),
        "to": args.end or now.isoformat(),
    }
    if args.max_alt is not None:
        params["max_alt_ft"] = args.max_alt
    url = "https://api.flyitalyadsb.com/v2/overflights?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-Api-Key": os.environ["FLYITALYADSB_API_KEY"], "User-Agent": "flyitalyadsb-overflights-example/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")

    print(f"{data['count']} aircraft within {data['dist_km']:g} km of {data['lat']}, {data['lon']}, "
          f"{data['from']} to {data['to']}")
    print(f"{'closest (UTC)':20} {'km':>5} {'lowest':>8}  {'callsign':9} {'reg':8} {'type':5} source")
    for o in data["overflights"]:
        low = o.get("min_alt_ft")
        low = low if low == "ground" else (f"{low:,.0f}" if low is not None else "-")
        print(f"{o['closest_time'][:19].replace('T', ' '):20} {o['closest_km']:5.1f} {low:>8}  "
              f"{(o.get('callsigns') or ['-'])[0]:9} {o.get('r') or '-':8} {o.get('t') or '-':5} {o.get('source', '')}")
    if data.get("truncated"):
        print(f"More results: ask again from {data['complete_until']}")
    for gap in data["coverage"].get("gaps", []):
        print(f"Not searched: {gap['from']} to {gap['to']} ({gap.get('reason', '')})")


if __name__ == "__main__":
    main()
