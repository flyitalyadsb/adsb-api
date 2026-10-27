# Free ADS-B flight tracking API: FlyItalyADSB

**Live aircraft positions as JSON, for any point on Earth.** One `curl` returns every aircraft within a radius of a point (position, altitude, speed, callsign, registration, type, squawk, military/PIA/LADD flags), from a community network of <!-- sync:receivers:start -->about 3,200<!-- sync:receivers:end --> ADS-B and MLAT receivers. The key is free and self-serve, and commercial use is allowed on every plan, Free included, within its limits.

[Get a free API key](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key) ·
[API docs](https://flyitalyadsb.com/en/data/api/docs/?utm_source=github&utm_campaign=adsb-api) ·
[OpenAPI spec](openapi/openapi.json) ·
[Examples](#examples) ·
[Plans](#plans-and-limits) ·
[FAQ](#faq) ·
[MCP server for AI assistants](#use-it-from-an-ai-assistant-mcp) ·
[Live map](https://mappa.flyitalyadsb.com/?utm_source=github&utm_campaign=adsb-api)

```bash
curl -H "X-Api-Key: $FLYITALYADSB_API_KEY" \
  https://api.flyitalyadsb.com/v2/lat/51.47/lon/-0.45/dist/25
```

## Quickstart (30 seconds)

1. **Get a key.** Enter your email on the [API page](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#api-key). You get a link that shows the key once. There is no approval step.
2. **Keep it out of your code.**
   ```bash
   export FLYITALYADSB_API_KEY=your-key   # or put it in a git-ignored .env, see .env.example
   ```
3. **Ask for the aircraft around a point** (here 25 km around London Heathrow; the radius is in kilometres):
   ```bash
   curl -H "X-Api-Key: $FLYITALYADSB_API_KEY" \
     https://api.flyitalyadsb.com/v2/lat/51.47/lon/-0.45/dist/25
   ```
4. **Read the JSON.** `now` is Unix seconds, `ac` has one record per aircraft in [readsb's aircraft.json format](https://github.com/wiedehopf/readsb/blob/dev/README-json.md), the same as tar1090 and adsb.lol. Shortened, real values:
   ```json
   {
     "now": 1793114821.1,
     "count": 30,
     "total": 30,
     "ac": [
       { "hex": "40838b", "type": "adsb_icao", "flight": "BAW486L ", "r": "G-TTSI", "t": "A20N",
         "lat": 51.380496, "lon": -0.645676, "alt_baro": 5050, "alt_geom": 5200,
         "gs": 254.0, "track": 199.79, "baro_rate": 1344, "squawk": "2043",
         "category": "A3", "seen_pos": 0.4 }
     ]
   }
   ```
   Altitudes are in feet (`alt_baro` is the string `"ground"` on the ground), speeds in knots, vertical rate in ft/min. `flight` is space-padded: trim it. Every field: [fields and units](https://flyitalyadsb.com/en/data/api/docs/fields/?utm_source=github&utm_campaign=adsb-api).

## Endpoints

Base URL `https://api.flyitalyadsb.com/v2`. Every request carries the key in the `X-Api-Key` header and gets JSON back; all are `GET` except webhook management. The machine-readable description is [openapi/openapi.json](openapi/openapi.json) (OpenAPI 3.1).

| Endpoint | Returns |
| --- | --- |
| `/lat/{lat}/lon/{lon}/dist/{km}` | Every aircraft within `km` kilometres of a point, anywhere in the world |
| `/icao/{hex}` · `/callsign/{callsign}` · `/reg/{reg}` | One aircraft by ICAO address, callsign or registration (404 when it isn't seen now) |
| `/mil` · `/pia` · `/ladd` | Military, PIA and LADD aircraft seen now, network-wide |
| `/sqk/{squawk}` · `/type/{type}` | Aircraft squawking a code (7700, 7600, 7500) or of an ICAO type (A320, B738, R44) |
| `/profile/{icao}` | One aircraft in one call: identity, live status, first and last day in the history |
| `/history/{icao}` · `/history/{icao}/{YYYY-MM-DD}` | The days with a track for an aircraft, and one day's track (since 2022, with gaps) |
| `/overflights?lat=&lon=&dist=&from=&to=` | The aircraft that flew over a place between two times (since 2026-08-17) |
| `/events?lat=&lon=&dist=` | Emergencies, military and other notable traffic in an area, up to 7 days back |
| `POST /webhooks` | The same events pushed to your URL, signed (paid plans) |

Coming from ADSBx v2? The records and most route names are the same. Here the radius is in **kilometres**, `/icao`, `/callsign` and `/reg` return the aircraft object rather than a list, and `now` is in seconds. Details: [migration notes](https://flyitalyadsb.com/en/data/api/docs/endpoints/?utm_source=github&utm_campaign=adsb-api#migrating).

## What people build with it

- **Desk, LED and e-paper flight displays** (ESP32, Raspberry Pi): "what's that plane over my house". The biggest group. Start from the [ESP32 sketch](examples/esp32/planes-overhead/) and the [displays and devices guide](https://flyitalyadsb.com/en/data/products/displays-and-devices/?utm_source=github&utm_campaign=adsb-api).
- **Plane-spotting apps and websites**: live traffic around airports, rare types (`/type/{type}`), aircraft profiles. See the [apps guide](https://flyitalyadsb.com/en/data/products/apps/?utm_source=github&utm_campaign=adsb-api) (key on your server, one cache for all users).
- **Drones and search-and-rescue awareness**: what's flying low nearby. Read the [drones guide](https://flyitalyadsb.com/en/data/products/drones/?utm_source=github&utm_campaign=adsb-api) first. This is not a certified tool and never for collision avoidance.
- **OSINT and military traffic**: unfiltered data, military aircraft included (many via MLAT), `/mil`, `/events`.
- **Aircraft noise monitoring**: `/overflights` answers "what flew over this address between 6 and 7 am", with the closest distance and the lowest altitude. See [overflights.py](examples/python/overflights.py).
- **Helicopter tracking**: rotorcraft that broadcast an emitter category carry `category: "A7"`; or query a type such as `/type/EC35`.

## Examples

All examples read the key from the `FLYITALYADSB_API_KEY` environment variable and have no third-party dependencies unless noted.

| Example | What it does |
| --- | --- |
| [`examples/curl.sh`](examples/curl.sh) | curl + jq: a radius, one aircraft by callsign, squawk 7700, military traffic, your usage headers, coverage of an area |
| [`examples/python/quickstart.py`](examples/python/quickstart.py) | The smallest Python client (standard library) |
| [`examples/python/near_me.py`](examples/python/near_me.py) | "Aircraft near me" CLI: nearest first, with distance and direction, `--watch` to refresh, handles 403/429 |
| [`examples/python/overflights.py`](examples/python/overflights.py) | What flew over a place in a time window (noise, helicopters, "what was that?") |
| [`examples/python/cache_server.py`](examples/python/cache_server.py) | One key for a whole product: your server fetches once every 30 s, your devices ask your server |
| [`examples/node/near.mjs`](examples/node/near.mjs) | Node.js 18+ with built-in `fetch` |
| [`examples/esp32/planes-overhead/`](examples/esp32/planes-overhead/) | ESP32 desk display of the planes overhead (serial monitor or SSD1306 OLED; ArduinoJson) |

```bash
export FLYITALYADSB_API_KEY=your-key
python3 examples/python/near_me.py 40.64 -73.78 -r 50     # 50 km around New York JFK
```

## Coverage

The network is global: born in Italy in 2020, with receivers all over the world. The API answers for any point on Earth.
<!-- sync:coverage:start -->
Of the receivers that share their position, about 36% are in the United States, 15% in Germany, 11% in the UK and Ireland and 16% in the rest of Europe; Asia, Australia and New Zealand follow; Latin America and Africa are thinner; Italy is about 3% (October 2026).
<!-- sync:coverage:end -->

On top of plain ADS-B, the network's own multilateration (MLAT) locates aircraft that don't broadcast a position, many military ones included.

Check your area before you build on it:

- the [coverage tool](https://flyitalyadsb.com/en/data/coverage/?utm_source=github&utm_campaign=adsb-api): aircraft seen in the last 24 hours, position freshness and receivers around any place;
- the same as JSON, no key needed (30 requests a minute per IP):
  ```bash
  curl -A "my-app/1.0" "https://api.flyitalyadsb.com/api/coverage?lat=45.46&lon=9.19&radius=100"
  ```
- or a request with a Free key, or a look at the [live map](https://mappa.flyitalyadsb.com/?utm_source=github&utm_campaign=adsb-api).

Freshness: the picture is rebuilt every 2 seconds and the API reloads it at most every 3; each aircraft carries `seen_pos`, and positions older than about 60 seconds are not returned.

## Plans and limits

FlyItalyADSB is a community project. The map and the Free plan stay free, commercial use included, within their limits. Paid plans are for heavy API users and help cover the cost of servers and bandwidth. A paid plan raises the limits of the key you already have.

Choose mostly by area: each request asks for the aircraft in a circle, and the largest circle depends on the plan.

<!-- sync:plans:start -->
| Plan | Price | Requests/min (per key) | Requests/month | Radius per request |
| --- | --- | --- | --- | --- |
| Free | €0 | 30 | 300,000 | up to 500 km |
| Starter | €9/month + tax | 60 | 1,000,000 | up to 1,000 km |
| Pro | €49/month + tax | 300 | 10,000,000 | whole world |
| Business | €249/month + tax | 1,000 | 50,000,000 | whole world |

- The Free plan also has a cap of 100 requests a minute per IP.
- The whole world in one request (`/lat/0/lon/0/dist/20040`) needs Pro or Business.
<!-- sync:plans:end -->

- Over a limit you get `429` (with `Retry-After`) or `403` for too large a radius. Refused requests are not counted and nothing is ever billed beyond the plan.
- The monthly counter resets on the 1st.
- Every response carries `X-FIA-Plan`, `X-FIA-Limit-Per-Min`, `X-FIA-Quota-Month` and `X-FIA-Used-Month`.
- No plan includes an SLA or guaranteed response times; the service is best effort.
- **Run a receiver?** Feeders get Pro limits on their Free keys at no cost, for non-commercial use. It's how the network grows: [become a feeder](https://flyitalyadsb.com/en/community/feeder/?utm_source=github&utm_campaign=adsb-api), then turn the perk on in [My API](https://flyitalyadsb.com/en/data/api/account/?utm_source=github&utm_campaign=adsb-api).
- Reselling the data as an API or feed for other people's products, an SLA, or volume beyond Business: [get in touch](https://flyitalyadsb.com/en/contact/?utm_source=github&utm_campaign=adsb-api).

Current prices and limits are always on the [plans page](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api#piani).

## Licence and credit

The only thing we ask is a credit with the licence, where your users see the data (in the app, on the device or in its manual, on the product page):

```text
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
```

If space is tight: `Data: flyitalyadsb.com (CC BY-SA 4.0)`. Your app's code, artwork and design stay yours. The details are in [using the data in a product](https://flyitalyadsb.com/en/data/products/using-the-data/?utm_source=github&utm_campaign=adsb-api#licence) and the [terms of service](https://flyitalyadsb.com/en/terms/?utm_source=github&utm_campaign=adsb-api).

**This repository:** the code (examples and scripts) is [MIT](LICENSE). The flight data the API returns is not MIT: it is CC BY-SA 4.0 under the API terms. See [NOTICE](NOTICE).

## FAQ

### Can I use it in a product I sell?

Yes, on every plan, Free included, within the plan's limits: apps, devices, websites and services, paid ones too. No separate agreement is needed. One is only needed to resell the data as an API or feed for other people's products.

### One key per device, or one per product? Can my server cache the data?

One key per product. Requests from all your devices, users and servers count together on it, from any IP. A key inside firmware or an app can be extracted, so from a few dozen units let your own server fetch once and serve your devices ([cache_server.py](examples/python/cache_server.py)). A caching server that serves only your own users is fine on every plan; it is not redistribution.

### What does the licence require?

A credit line with the licence: `Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0`. See [Licence and credit](#licence-and-credit).

### What's the coverage in my area?

Check it with the [coverage tool](https://flyitalyadsb.com/en/data/coverage/?utm_source=github&utm_campaign=adsb-api) or its keyless JSON (see [Coverage](#coverage)), or try a request with a Free key.

### Which plan do I need, and what happens over the limit?

Pick by radius first, then size the volume as requests per minute per device × devices, and compare with the [plans table](#plans-and-limits). One device asking every 30 seconds makes 86,400 requests a month; a server fetching once every 30 seconds for any number of users is also 86,400 a month. Over a limit you get 429 or 403, never a bill. More worked examples: [plan and limits](https://flyitalyadsb.com/en/data/products/using-the-data/?utm_source=github&utm_campaign=adsb-api#plan).

### Are routes, military aircraft and squawk codes in the data?

- Routes (departure and arrival airports), airlines, schedules and photos: **no**. For those you need another source.
- Military: **yes**. The data is unfiltered: military, PIA and LADD aircraft are flagged, not hidden. `dbFlags & 1` marks military (2 interesting, 4 PIA, 8 LADD), and `/mil` lists them all.
- Squawk: **yes**, `squawk` on every record that transmits one, and `/sqk/7700` finds emergencies network-wide.
- Registration and ICAO type are present for about 99% of aircraft.

### Is there history?

Yes, self-serve with the same key: per-aircraft daily tracks since 2022 (with gaps; every day since 2026-08-17) and overflights of a place since 2026-08-17. See [history](https://flyitalyadsb.com/en/data/api/docs/history/?utm_source=github&utm_campaign=adsb-api).

### Can I call it from a web page?

CORS is open, but a key in a web page is public. Call the API from your server.

### I get an HTML page ("Attention Required", error 1010 or 1020) instead of JSON.

The request was stopped before the API. Always send `X-Api-Key`, and send a `User-Agent` of your own (your app's name). If it goes on, see [limits and errors](https://flyitalyadsb.com/en/data/api/docs/limits-and-errors/?utm_source=github&utm_campaign=adsb-api#blocked-by-cloudflare).

### How does it compare with other ADS-B APIs?

See the factual [ADS-B API comparison](https://flyitalyadsb.com/en/data/comparison/?utm_source=github&utm_campaign=adsb-api): rate limits, feeder requirements and commercial-use terms of each.

More answers in the [FAQ](https://flyitalyadsb.com/en/faq/?utm_source=github&utm_campaign=adsb-api).

## Use it from an AI assistant (MCP)

The same data is available to Claude, ChatGPT and other assistants through an MCP server at `https://flyitalyadsb.com/mcp` (Streamable HTTP), listed in the official MCP registry as `com.flyitalyadsb/mcp`. Ask "which aircraft are near Rome Fiumicino right now?" and, in Claude and ChatGPT, the answer comes with an interactive map in the chat.

- **claude.ai**: Connectors → Add custom connector → URL `https://flyitalyadsb.com/mcp` → Connect (sign in with your email and a 6-digit code; a free key is created if you have none).
- **Claude Code** and clients without OAuth, with your key:
  ```bash
  claude mcp add --transport http flyitalyadsb https://flyitalyadsb.com/mcp \
    --header "X-Api-Key: $FLYITALYADSB_API_KEY"
  ```

Tools: `find_aircraft`, `aircraft_near`, `special_traffic`, `aircraft_history`, `aircraft_profile`, `overflights`, `notable_traffic`, `set_my_location`, `clear_my_location`. Each tool call counts as one request on your key. Guide: [MCP and AI agents](https://flyitalyadsb.com/en/data/mcp/?utm_source=github&utm_campaign=adsb-api).

For agents and LLMs: [`llms.txt`](llms.txt) in this repository summarises the API, and the site publishes [its own](https://flyitalyadsb.com/llms.txt) plus an [API catalog](https://flyitalyadsb.com/.well-known/api-catalog).

## Kept in sync with the live API

This repository keeps itself in sync with the live API and site. Every day the [sync workflow](.github/workflows/sync.yml) runs [`scripts/sync.py`](scripts/sync.py), which:

- copies the published spec, `https://flyitalyadsb.com/openapi.json`, into [`openapi/openapi.json`](openapi/openapi.json) (pretty-printed, so changes diff cleanly);
- regenerates the parts of this README and of [`llms.txt`](llms.txt) between `<!-- sync:… -->` markers (plans and limits, receiver count and coverage shares) from the live site;
- checks that every endpoint, parameter and field the examples use is still in the spec, and that the examples' default radii still fit the Free plan;
- commits only if something changed, and fails without committing if anything doesn't parse or a check fails.

```bash
python3 scripts/sync.py --dry-run   # what would change; exit 1 if the repo is out of date
```

## Links

- [REST API page, plans and free key](https://flyitalyadsb.com/en/data/api/?utm_source=github&utm_campaign=adsb-api)
- [API documentation](https://flyitalyadsb.com/en/data/api/docs/?utm_source=github&utm_campaign=adsb-api) · [changelog](https://flyitalyadsb.com/en/data/api/docs/changelog/?utm_source=github&utm_campaign=adsb-api)
- [For product builders](https://flyitalyadsb.com/en/data/products/?utm_source=github&utm_campaign=adsb-api)
- [Service status](https://flyitalyadsb.com/en/status/?utm_source=github&utm_campaign=adsb-api)
- [Become a feeder](https://flyitalyadsb.com/en/community/feeder/?utm_source=github&utm_campaign=adsb-api) · [the network](https://flyitalyadsb.com/en/network/?utm_source=github&utm_campaign=adsb-api)
- [Contact](https://flyitalyadsb.com/en/contact/?utm_source=github&utm_campaign=adsb-api)

Found a problem in an example? Open an issue in this repository.

---

Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0. Service provided by Nesso Labs S.r.l.
