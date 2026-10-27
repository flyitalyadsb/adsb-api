#!/usr/bin/env python3
"""Aircraft near me: the aircraft around a point, nearest first.

    export FLYITALYADSB_API_KEY=...         # free: https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key
    python3 near_me.py 51.47 -0.45          # 25 km around London Heathrow
    python3 near_me.py 40.64 -73.78 -r 50   # 50 km around New York JFK
    python3 near_me.py 45.46 9.19 --watch 30
    python3 near_me.py                      # the position saved in My API or via the MCP server

Python 3.8+, standard library only.
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.flyitalyadsb.com/v2"
USER_AGENT = "flyitalyadsb-near-me-example/1.0"
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class ApiError(Exception):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def get(path, key):
    req = urllib.request.Request(API + path, headers={"X-Api-Key": key, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except ValueError:  # an HTML page: stopped at the edge, before the API
            raise ApiError(f"HTTP {e.code} from the edge, not the API: check the X-Api-Key header") from None
        message = f"HTTP {e.code}: {body.get('error', raw[:200])}"
        if body.get("help"):
            message += f"\n  see {body['help']}"
        raise ApiError(message, e.headers.get("Retry-After")) from None


def distance_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    h = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def bearing(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    y = math.sin((lon2 - lon1) * p) * math.cos(lat2 * p)
    x = (math.cos(lat1 * p) * math.sin(lat2 * p)
         - math.sin(lat1 * p) * math.cos(lat2 * p) * math.cos((lon2 - lon1) * p))
    return COMPASS[round((math.atan2(y, x) / p % 360) / 45) % 8]


def show(lat, lon, radius, limit, key):
    data = get(f"/lat/{lat}/lon/{lon}/dist/{radius}", key)
    rows = []
    for a in data["ac"]:
        if "lat" not in a:
            continue
        alt = a.get("alt_baro")
        rows.append((
            distance_km(lat, lon, a["lat"], a["lon"]),
            a.get("flight", "").strip() or "-",
            a.get("r") or "-",
            a.get("t") or "-",
            "ground" if alt == "ground" else (f"{alt:,} ft" if isinstance(alt, (int, float)) else "-"),
            f"{a['gs']:.0f} kt" if "gs" in a else "-",
            bearing(lat, lon, a["lat"], a["lon"]),
            ("MLAT" if a.get("type") == "mlat" else "")
            + (" MIL" if a.get("dbFlags", 0) & 1 else ""),
        ))
    rows.sort()
    print(f"\n{len(rows)} aircraft within {radius:g} km of {lat}, {lon} at {time.strftime('%H:%M:%S')}")
    print(f"{'km':>5}  {'callsign':8} {'reg':8} {'type':5} {'altitude':>10} {'speed':>7}  dir")
    for km, callsign, reg, typ, alt, gs, direction, notes in rows[:limit]:
        print(f"{km:5.1f}  {callsign:8} {reg:8} {typ:5} {alt:>10} {gs:>7}  {direction:3} {notes}")
    if len(rows) > limit:
        print(f"... and {len(rows) - limit} more")


def main():
    parser = argparse.ArgumentParser(description="Aircraft near a point, nearest first.")
    parser.add_argument("lat", type=float, nargs="?", help="latitude (default: your saved position)")
    parser.add_argument("lon", type=float, nargs="?", help="longitude")
    parser.add_argument("-r", "--radius", type=float, default=25, help="radius in km (default 25)")
    parser.add_argument("-n", "--limit", type=int, default=20, help="rows to show (default 20)")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="refresh every SECONDS (at least 15)")
    args = parser.parse_args()

    key = os.environ.get("FLYITALYADSB_API_KEY")
    if not key:
        sys.exit("Set FLYITALYADSB_API_KEY: a free key takes a minute at "
                 "https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key")

    try:
        lat, lon = args.lat, args.lon
        if lat is None or lon is None:
            saved = get("/me/location", key)["location"]  # not counted as a request
            if not saved:
                sys.exit("No position saved on this key: pass LAT LON, or save one in My API "
                         "(https://flyitalyadsb.com/en/data/api/account/?utm_source=github&utm_campaign=adsb-api).")
            lat, lon = saved["lat"], saved["lon"]
        while True:
            try:
                show(lat, lon, args.radius, args.limit, key)
            except ApiError as e:
                if not (args.watch and e.retry_after):
                    raise
                print(f"{e} - retrying in {e.retry_after} s", file=sys.stderr)
                time.sleep(int(e.retry_after))
                continue
            if not args.watch:
                break
            time.sleep(max(args.watch, 15))
    except ApiError as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
