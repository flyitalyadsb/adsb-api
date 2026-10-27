#!/usr/bin/env python3
"""One key for a whole product: your server fetches once, your devices ask your server.

Your server asks the API for one area every 30 seconds and keeps the answer in
memory; each device or app user asks your server for the aircraft near it. Usage
stays at 2 requests a minute (86,400 a month) however many devices you sell, and
the key never leaves your server. This is allowed on every plan: it serves only
your own product's users.

    export FLYITALYADSB_API_KEY=...
    python3 cache_server.py                         # 500 km around 51.5, -0.1 (Free plan maximum)
    AREA=0,0,20040 python3 cache_server.py          # the whole world (Pro and Business)
    curl "localhost:8080/near?lat=51.47&lon=-0.45&km=15"

Python 3.8+, standard library only.
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
"""

import gzip
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

KEY = os.environ["FLYITALYADSB_API_KEY"]
LAT, LON, KM = (float(x) for x in os.environ.get("AREA", "51.5,-0.1,500").split(","))
SOURCE = f"https://api.flyitalyadsb.com/v2/lat/{LAT}/lon/{LON}/dist/{KM}"
EVERY_S = 30
HOST = os.environ.get("HOST", "127.0.0.1")  # 0.0.0.0 to serve other machines
PORT = int(os.environ.get("PORT", "8080"))

snapshot = {"now": 0, "ac": []}


def refresh_forever():
    while True:
        wait = EVERY_S
        try:
            req = urllib.request.Request(SOURCE, headers={
                "X-Api-Key": KEY, "Accept-Encoding": "gzip", "User-Agent": "my-product-backend/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            data = json.loads(body)
            snapshot.update(now=data["now"], ac=[a for a in data["ac"] if "lat" in a])
            print(f"{len(snapshot['ac'])} aircraft cached")
        except urllib.error.HTTPError as e:  # keep serving the last copy
            print("refresh failed:", e.code, e.read()[:200])
            wait = max(EVERY_S, int(e.headers.get("Retry-After") or 0))
        except Exception as e:
            print("refresh failed:", e)
        time.sleep(wait)


def distance_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    h = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


class Near(BaseHTTPRequestHandler):
    def do_GET(self):  # /near?lat=51.47&lon=-0.45&km=15
        url = urlparse(self.path)
        if url.path != "/near":
            return self.reply(404, {"error": "not found"})
        try:
            q = {k: float(v[0]) for k, v in parse_qs(url.query).items()}
            lat, lon, km = q["lat"], q["lon"], min(q.get("km", 15), 200)
        except (KeyError, ValueError):
            return self.reply(400, {"error": "use /near?lat=..&lon=..&km=.."})
        ac = [a for a in snapshot["ac"] if distance_km(lat, lon, a["lat"], a["lon"]) <= km]
        self.reply(200, {"now": snapshot["now"], "count": len(ac), "ac": ac,
                         "credit": "Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0"})

    def reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=refresh_forever, daemon=True).start()
    print(f"caching {SOURCE} every {EVERY_S} s; serving http://{HOST}:{PORT}/near?lat=..&lon=..&km=..")
    ThreadingHTTPServer((HOST, PORT), Near).serve_forever()
