#!/usr/bin/env python3
"""Every aircraft within 25 km of London Heathrow, right now.

    export FLYITALYADSB_API_KEY=...   # free: https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key
    python3 quickstart.py

Python 3.8+, standard library only.
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
"""

import json
import os
import urllib.request

URL = "https://api.flyitalyadsb.com/v2/lat/51.47/lon/-0.45/dist/25"

req = urllib.request.Request(URL, headers={
    "X-Api-Key": os.environ["FLYITALYADSB_API_KEY"],
    "User-Agent": "my-app/1.0",  # name your app: Python's default User-Agent is refused on some endpoints
})
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.load(r)

print(f"{data['count']} aircraft")
for a in data["ac"]:
    callsign = a.get("flight", "").strip() or "-"
    alt = a.get("alt_baro", "?")  # feet, or the string "ground"
    print(f"{callsign:8} {a.get('r', '-'):8} {a.get('t', '-'):5} {alt}")
