# flyitalyadsb: official Python client for the FlyItalyADSB ADS-B API

**flyitalyadsb** is the official Python client for the [FlyItalyADSB](https://flyitalyadsb.com/en/data/api/?utm_source=pypi&utm_campaign=python-client) ADS-B API: live and historical aircraft positions as JSON for any point on Earth, from a community network of about 3,200 ADS-B and MLAT receivers. Commercial use is allowed on every plan, Free included. The Free key is self-serve and answers up to 500 km around a point; the Pro plan (€49/month) returns the whole world in one request. The data is unfiltered: military, PIA and LADD aircraft are flagged, not removed, and the network's own MLAT locates aircraft that don't broadcast a position. Beyond live positions there are per-aircraft history, overflights of a place, notable-traffic events and an MCP server for AI assistants. Standard library only (no dependencies), fully typed, Python 3.9+.

```bash
pip install flyitalyadsb
```

## Quickstart

Get a free key with your email on the [API page](https://flyitalyadsb.com/en/data/api/?utm_source=pypi&utm_campaign=python-client#api-key) (no approval step), then:

```python
from flyitalyadsb import Client

client = Client()  # reads the key from FLYITALYADSB_API_KEY, or Client(api_key="...")

# Every aircraft within 25 km of London Heathrow, right now
for a in client.near(51.47, -0.45, 25):
    print(a.callsign, a.registration, a.icao_type, a.altitude, "MIL" if a.military else "")

print(client.limits)  # your plan and usage this month, from the X-FIA-* headers
```

Keep the key out of your code and out of git: an environment variable, or your secret store.

## Methods

Every method is one request on your key; the account calls through `request()` (`/me/location`, `/webhooks`) are not counted. Radii are in kilometres.

| Method | Endpoint | Returns |
| --- | --- | --- |
| `near(lat, lon, radius_km)` | `/lat/{lat}/lon/{lon}/dist/{km}` | `AircraftList`: every aircraft within the radius, anywhere on Earth |
| `world()` | `/lat/0/lon/0/dist/20040` | `AircraftList`: the whole world in one request (Pro and Business plans) |
| `by_icao(icao)` | `/icao/{hex}` | `Aircraft`, or `None` if it isn't seen now |
| `by_callsign(callsign)` | `/callsign/{callsign}` | `Aircraft` or `None` |
| `by_registration(registration)` | `/reg/{reg}` | `Aircraft` or `None` |
| `military()`, `pia()`, `ladd()` | `/mil`, `/pia`, `/ladd` | `AircraftList`: military, PIA and LADD aircraft seen now, network-wide |
| `squawk(code)` | `/sqk/{squawk}` | `AircraftList`: e.g. `7700`, `7600`, `7500`, network-wide |
| `aircraft_type(designator)` | `/type/{type}` | `AircraftList`: an ICAO type, e.g. `"A320"`, `"B738"`, `"EC35"` |
| `history(icao)` | `/history/{icao}` | `HistoryDates`: the UTC days with a track |
| `history(icao, day)` | `/history/{icao}/{date}` | `Trace` or `None`: one day's track, `positions()` for the points |
| `profile(icao)` | `/profile/{icao}` | `Profile` or `None`: identity, live status, history summary, links |
| `overflights(lat, lon, radius_km, start, end)` | `/overflights` | `Overflights`: the aircraft that flew over a place between two times |
| `events(lat, lon, radius_km, since=, until=, kinds=)` | `/events` | `Events`: emergencies, military and other notable traffic, up to 7 days back |
| `request(method, path, params=, body=)` | any other, e.g. `/me/location`, `/webhooks` | the parsed JSON |
| `request_key(email, found_via="pypi")` (a function) | `POST /keys` | asks for a free key: the address gets a one-time link. Never called for you |

`Aircraft` has typed fields with readable names (`callsign`, `registration`, `icao_type`, `lat`, `lon`, `altitude` in feet or `"ground"`, `ground_speed` in knots, `vertical_rate` in ft/min, `squawk`, `source` such as `adsb_icao` or `mlat`, `db_flags`) and the flags `military`, `interesting`, `pia`, `ladd`, `on_ground` and `from_mlat`. Every field the API sent stays available with its own name in `raw` and through `get()`, e.g. `a.get("nav_altitude_mcp")`. Lists are iterable and have `len()`. Every result keeps the full JSON in `raw`. The fields and units: [fields and units](https://flyitalyadsb.com/en/data/api/docs/fields/?utm_source=pypi&utm_campaign=python-client).

```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)

# What flew within 3 km of a place in the last 2 hours, with the lowest altitude in the circle
for o in client.overflights(45.4642, 9.19, 3, now - timedelta(hours=2), now):
    print(o.closest_time, o.registration, o.icao_type, o.callsigns, o.min_alt_ft, o.closest_km)

# Emergencies and military traffic within 100 km in the last 24 hours
for e in client.events(45.54, 10.22, 100, kinds=["emergency", "military"]):
    print(e.time, e.kind, e.reason, e.callsign, e.registration, e.map_url)

# One aircraft's days with a track, and its last day's track
dates = client.history("4ca7b5")
if dates.dates:
    track = client.history("4ca7b5", dates.dates[-1])
    print(len(track.positions()) if track else 0, "points")
```

## Plans and limits

Choose mostly by area: each request asks for the aircraft in a circle, and the largest circle depends on the plan. Commercial use is allowed on every plan, Free included.

| Plan | Price per month (before tax) | Requests/min (per key) | Requests/month | Radius per request | Overflights |
| --- | --- | --- | --- | --- | --- |
| Free | €0 | 30 | 300,000 | up to 500 km | 10 km, 6 h window |
| Starter | €9 | 60 | 1,000,000 | up to 1,000 km | 25 km, 24 h |
| Pro | €49 | 300 | 10,000,000 | whole world | 50 km, 24 h |
| Business | €249 | 1,000 | 50,000,000 | whole world | 50 km, 24 h |

- The Free plan also has a cap of 100 requests a minute per IP.
- A paid plan raises the limits of the key you already have.
- Requests refused for a limit are not counted, and nothing is ever billed beyond the plan.
- The monthly counter resets on the 1st. No plan includes an SLA: the service is best effort.
- Current prices and limits are always on the [plans page](https://flyitalyadsb.com/en/data/api/?utm_source=pypi&utm_campaign=python-client#piani).

`client.limits` (and `.limits` on every result) reports the key's state from the `X-FIA-Plan`, `X-FIA-Limit-Per-Min`, `X-FIA-Quota-Month` and `X-FIA-Used-Month` headers: `plan`, `limit_per_min`, `quota_month`, `used_month` and `remaining_month`.

## Errors

| Exception | When | Useful attributes |
| --- | --- | --- |
| `PlanLimitError` | 403 or 429: a limit of the plan | `reason` (`"radius"`, `"overflights"`, `"paid_plan"`, `"rate_limit"`, `"monthly_quota"`), `max_radius_km`, `retry_after`, `resets`, `plans_url` |
| `AuthError` | 401: missing or invalid key | `help_url` |
| `NotFoundError` | 404 (the lookups return `None` instead) | |
| `ApiError` | any other error answer, e.g. 400 | `status`, `message`, `code`, `body`, `limits` |
| `TransportError` | no usable answer: network, timeout, not JSON | |

All of them are `FlyItalyADSBError`.

```python
from flyitalyadsb import Client, PlanLimitError

client = Client(user_agent="my-app/1.0")  # name your app in the User-Agent
try:
    everything = client.world()
except PlanLimitError as e:
    if e.reason == "radius":  # Free and Starter: 500 and 1,000 km per request
        print(f"Up to {e.max_radius_km:g} km on this plan; the whole world needs Pro: {e.plans_url}")
    elif e.reason == "monthly_quota":
        print("Monthly quota used up until", e.resets, e.plans_url)
    else:
        print(e)
```

The client never hammers the API. On a 429 or 503 that carries `Retry-After` of at most `max_retry_wait` seconds (default 30), it waits once and tries again; otherwise it raises. Radius and monthly-quota errors are never retried. The timeout is 30 seconds by default (`Client(timeout=...)`).

## What's in the data

- One record per aircraft in readsb's aircraft.json format: ICAO address, position, altitude, speed, track, vertical rate, squawk, category, and the military, PIA and LADD flags. Registration and ICAO type are present for about 99% of aircraft, callsign for about 98%.
- Unfiltered: military, PIA and LADD aircraft are flagged, not hidden. Positions from ADS-B and from the network's own MLAT, which covers many military aircraft.
- The picture refreshes every half second. Coverage follows the receivers, worldwide: check an area with the [coverage tool](https://flyitalyadsb.com/en/data/coverage/?utm_source=pypi&utm_campaign=python-client) before you build on it.
- History: per-aircraft daily tracks for every day since 2026-08-17, plus 2022 to 2024 with gaps. Overflights of a place since 2026-08-17.
- Not included: routes (departure and arrival airports), schedules and photos.

## Licence and credit

The flight data is licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The only thing asked is a credit with the licence where your users see the data (in the app, on the device or in its manual, on the product page), with a link to flyitalyadsb.com:

```text
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
```

The same line is `flyitalyadsb.ATTRIBUTION`. Share-alike covers the data and adapted versions of it (a dataset, feed or API built from it), not your product's code, artwork or design. Details: [using the data in a product](https://flyitalyadsb.com/en/data/products/using-the-data/?utm_source=pypi&utm_campaign=python-client) and the [terms of service](https://flyitalyadsb.com/en/terms/?utm_source=pypi&utm_campaign=python-client).

The code of this package is [MIT](https://github.com/flyitalyadsb/adsb-api/blob/main/python/LICENSE); the data it returns is not MIT (see [NOTICE](https://github.com/flyitalyadsb/adsb-api/blob/main/python/NOTICE)).

## MCP server for AI assistants

The same data, with the same key, is available to AI assistants through an MCP server at `https://flyitalyadsb.com/mcp` (Streamable HTTP, listed in the official MCP registry as `com.flyitalyadsb/mcp`). On claude.ai: Connectors, Add custom connector, URL `https://flyitalyadsb.com/mcp`. In Claude Code:

```bash
claude mcp add --transport http flyitalyadsb https://flyitalyadsb.com/mcp \
  --header "X-Api-Key: $FLYITALYADSB_API_KEY"
```

Guide: [MCP and AI agents](https://flyitalyadsb.com/en/data/mcp/?utm_source=pypi&utm_campaign=python-client).

## Links

- [API page: plans and a free key](https://flyitalyadsb.com/en/data/api/?utm_source=pypi&utm_campaign=python-client)
- [API documentation](https://flyitalyadsb.com/en/data/api/docs/?utm_source=pypi&utm_campaign=python-client): [endpoints](https://flyitalyadsb.com/en/data/api/docs/endpoints/?utm_source=pypi&utm_campaign=python-client), [limits and errors](https://flyitalyadsb.com/en/data/api/docs/limits-and-errors/?utm_source=pypi&utm_campaign=python-client), [history](https://flyitalyadsb.com/en/data/api/docs/history/?utm_source=pypi&utm_campaign=python-client), [alerts and webhooks](https://flyitalyadsb.com/en/data/api/docs/alerts/?utm_source=pypi&utm_campaign=python-client), [commercial use](https://flyitalyadsb.com/en/data/api/docs/commercial-use/?utm_source=pypi&utm_campaign=python-client)
- [OpenAPI 3.1 spec](https://flyitalyadsb.com/openapi.json)
- [Examples and source on GitHub](https://github.com/flyitalyadsb/adsb-api) (curl, Python, Node.js, ESP32)
- [Service status](https://flyitalyadsb.com/en/status/?utm_source=pypi&utm_campaign=python-client) · [Contact](https://flyitalyadsb.com/en/contact/?utm_source=pypi&utm_campaign=python-client)

Found a bug in the client? [Open an issue](https://github.com/flyitalyadsb/adsb-api/issues).

---

Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0. Service provided by Nesso Labs S.r.l.
