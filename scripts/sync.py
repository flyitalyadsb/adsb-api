#!/usr/bin/env python3
"""Keep this repository in sync with the live API and site.

    python3 scripts/sync.py                 # regenerate, run the safety checks, write changes
    python3 scripts/sync.py --dry-run       # same, but write nothing; exit 1 if anything would change
    python3 scripts/sync.py --summary FILE  # also write a one-line summary of what changed

What it regenerates, and from where:
  openapi/openapi.json            https://flyitalyadsb.com/openapi.json
  receivers ("about 3,200")       info.description of that spec (must agree with the site's llms.txt)
  coverage percentages            the "Coverage" section of https://flyitalyadsb.com/llms.txt
  plans and limits                the plan tables on two live pages, which must agree:
                                  /en/data/api/docs/limits-and-errors/ and
                                  /en/data/products/using-the-data/
Generated text sits between <!-- sync:NAME:start --> and <!-- sync:NAME:end --> markers
in README.md and llms.txt; everything outside the markers is hand-written.

Before writing anything it checks that every endpoint, parameter and response field the
examples use still exists in the new spec, that the examples' default radii still fit the
Free plan, and that the keyless coverage endpoint still has the fields curl.sh reads.
Anything unexpected (a page that no longer parses, sources that disagree, a missing
marker) stops the run with an error, and nothing is written.

Python 3.8+, standard library only.
"""

import argparse
import html.parser
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://flyitalyadsb.com"
OPENAPI_URL = SITE + "/openapi.json"
OPENAPI_PATH = ROOT / "openapi" / "openapi.json"
# A User-Agent of our own: the site refuses Python's default "Python-urllib/x.y".
USER_AGENT = "flyitalyadsb-adsb-api-sync/1.0 (+https://github.com/flyitalyadsb/adsb-api)"


class SyncError(Exception):
    pass


def fail(message):
    raise SyncError(message)


# ---------------------------------------------------------------- fetching

_fetched = {}


def get(url, accept="*/*"):
    if url in _fetched:
        return _fetched[url]
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _fetched[url] = r.read().decode("utf-8")
    except Exception as e:
        fail(f"could not fetch {url}: {e}")
    return _fetched[url]


def fetch_openapi():
    """The live spec, pretty-printed (stable output, readable diffs)."""
    try:
        spec = json.loads(get(OPENAPI_URL, "application/json"))
    except ValueError as e:
        fail(f"{OPENAPI_URL} is not valid JSON: {e}")
    if not str(spec.get("openapi", "")).startswith("3."):
        fail(f"{OPENAPI_URL} is not an OpenAPI 3 document")
    if not spec.get("paths"):
        fail(f"{OPENAPI_URL} has no paths")
    return spec, json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- plans (HTML)

class Tables(html.parser.HTMLParser):
    """Every <table> on a page as rows of whitespace-normalised cell texts."""

    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
            self.tables[-1].append(self.row)
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def number(text, what):
    if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", text):
        fail(f"{what}: {text!r} is not a number")
    return int(text.replace(",", ""))


def plans_from_page(url):
    parser = Tables()
    parser.feed(get(url, "text/html"))
    found = []
    for table in parser.tables:
        if not table:
            continue
        head = [h.lower() for h in table[0]]
        cols = {
            "plan": [i for i, h in enumerate(head) if h == "plan"],
            "price": [i for i, h in enumerate(head) if "price" in h],
            "per_min": [i for i, h in enumerate(head) if "minute" in h],
            "per_month": [i for i, h in enumerate(head) if "month" in h and "minute" not in h],
            "radius": [i for i, h in enumerate(head) if "radius" in h],
        }
        if all(len(v) == 1 for v in cols.values()):
            found.append((table, {k: v[0] for k, v in cols.items()}, head))
    if len(found) != 1:
        fail(f"{url}: expected exactly one plan table (Plan, Price, minute, month, radius), found {len(found)}")
    table, col, head = found[0]
    if "before tax" not in head[col["price"]]:
        fail(f"{url}: the price column no longer says 'before tax': {head[col['price']]!r}")
    plans = []
    for row in table[1:]:
        if len(row) != len(head):
            fail(f"{url}: plan row {row!r} has {len(row)} cells, the header has {len(head)}")
        name = row[col["plan"]]
        if not re.fullmatch(r"[A-Z][A-Za-z]+", name):
            fail(f"{url}: unexpected plan name {name!r}")
        price_text = row[col["price"]]
        if price_text.lower() in ("free", "€0", "€0/month"):
            price = 0
        else:
            m = re.fullmatch(r"€\s?(\d+)(?:/month)?", price_text)
            if not m:
                fail(f"{url}: price {price_text!r} of {name} does not parse")
            price = int(m.group(1))
        radius_text = row[col["radius"]].lower()
        if radius_text in ("no limit", "whole world", "worldwide"):
            radius = None
        else:
            m = re.fullmatch(r"([\d,]+) km", radius_text)
            if not m:
                fail(f"{url}: radius {radius_text!r} of {name} does not parse")
            radius = number(m.group(1), f"{url} radius of {name}")
        plans.append({
            "name": name,
            "price_eur": price,
            "per_min": number(row[col["per_min"]], f"{url} per-minute of {name}"),
            "per_month": number(row[col["per_month"]], f"{url} per-month of {name}"),
            "radius_km": radius,
        })
    names = [p["name"] for p in plans]
    if "Free" not in names or len(names) < 2 or len(set(names)) != len(names):
        fail(f"{url}: implausible plan list {names}")
    return plans


def live_plans():
    a = plans_from_page(SITE + "/en/data/api/docs/limits-and-errors/")
    b = plans_from_page(SITE + "/en/data/products/using-the-data/")
    if a != b:
        fail(f"the two live plan tables disagree:\n  limits-and-errors: {a}\n  using-the-data:    {b}")
    page = " ".join(get(SITE + "/en/data/api/docs/limits-and-errors/", "text/html").split())
    m = re.search(r"Free plan also has a (?:limit|cap) of ([\d,]+) requests per minute per IP", page)
    if not m:
        fail("limits-and-errors: the Free plan's per-IP limit sentence is gone")
    return a, number(m.group(1), "per-IP limit")


# ---------------------------------------------------------------- coverage and receivers

def live_coverage(site_llms):
    m = re.search(
        r"\(([A-Z][a-z]+ \d{4}), receivers that share a position\): about (\d+)% in the United States, "
        r"(\d+)% in Germany, (\d+)% in the UK and Ireland, (\d+)% in the rest of Europe", site_llms)
    italy = re.search(r"Italy, where the project started in \d{4}, is about (\d+)%", site_llms)
    if not (m and italy):
        fail("the site's llms.txt 'Coverage' section no longer has the receiver shares in the expected form")
    month, us, de, uk, eu = m.groups()
    shares = [int(x) for x in (us, de, uk, eu, italy.group(1))]
    if not all(0 < s < 100 for s in shares) or sum(shares) > 100:
        fail(f"implausible receiver shares {shares}")
    return {"as_of": month, "us": us, "de": de, "uk": uk, "eu": eu, "it": italy.group(1)}


def live_receivers(spec, site_llms):
    a = re.search(r"about ([\d,]+) receivers", spec["info"].get("description", ""))
    b = re.search(r"about ([\d,]+) receivers", site_llms)
    if not (a and b):
        fail("'about N receivers' is missing from the spec's info.description or the site's llms.txt")
    if a.group(1) != b.group(1):
        fail(f"receivers disagree: spec says {a.group(1)}, site llms.txt says {b.group(1)}")
    number(a.group(1), "receivers")
    return a.group(1)


# ---------------------------------------------------------------- rendering

def km(radius):
    return "whole world" if radius is None else f"up to {radius:,} km"


def render(plans, per_ip, coverage, receivers):
    world = [p["name"] for p in plans if p["radius_km"] is None]
    world_text = " or ".join(world) if world else None
    rows = "\n".join(
        f"| {p['name']} | {'€0' if p['price_eur'] == 0 else '€%d/month + tax' % p['price_eur']} "
        f"| {p['per_min']:,} | {p['per_month']:,} | {km(p['radius_km'])} |" for p in plans)
    readme_plans = (
        "| Plan | Price | Requests/min (per key) | Requests/month | Radius per request |\n"
        "| --- | --- | --- | --- | --- |\n" + rows + "\n\n"
        f"- The Free plan also has a cap of {per_ip:,} requests a minute per IP.\n"
        + (f"- The whole world in one request (`/lat/0/lon/0/dist/20040`) needs {world_text}.\n"
           if world_text else ""))
    llms_plans = "\n".join(
        f"- {p['name']}: €{p['price_eur']}/month, {p['per_min']:,} requests/min per key, "
        f"{p['per_month']:,} requests/month, "
        + ("no radius limit (the whole world)." if p["radius_km"] is None else f"radius up to {p['radius_km']:,} km.")
        for p in plans) + "\n" + (
        f"- The Free plan also has a cap of {per_ip:,} requests/min per IP.\n")
    if world_text:
        llms_plans += f"- Whole world in one request (`/lat/0/lon/0/dist/20040`): {world_text}.\n"
    c = coverage
    shares = (
        f"about {c['us']}% are in the United States, {c['de']}% in Germany, {c['uk']}% in the UK and "
        f"Ireland and {c['eu']}% in the rest of Europe; Asia, Australia and New Zealand follow; "
        f"Latin America and Africa are thinner; Italy is about {c['it']}% ({c['as_of']}).\n")
    return {
        "README.md": {"plans": readme_plans, "receivers": f"about {receivers}",
                      "coverage": "Of the receivers that share their position, " + shares},
        "llms.txt": {"plans": llms_plans, "receivers": f"about {receivers}",
                     "coverage": "- Where the receivers are: of those that share their position, " + shares},
    }


def replace_blocks(text, blocks, filename):
    for name, body in blocks.items():
        start, end = f"<!-- sync:{name}:start -->", f"<!-- sync:{name}:end -->"
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
            fail(f"{filename}: markers {start} ... {end} missing, repeated or out of order")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        inline = not before.endswith("\n")
        text = before + start + (body.rstrip("\n") if inline else "\n" + body) + end + after
    return text


# ---------------------------------------------------------------- safety checks

# What the examples rely on. If the new spec drops or reshapes any of it, stop.
AIRCRAFT_FIELDS = ["hex", "type", "flight", "r", "t", "dbFlags", "lat", "lon", "alt_baro", "gs", "squawk"]
USES = [
    # method, path, query parameters, fields of the 200 response, used by
    ("get", "/v2/lat/{lat}/lon/{lon}/dist/{dist}", [], ["now", "count", "ac"],
     "quickstart.py, near_me.py, cache_server.py, near.mjs, curl.sh, planes-overhead.ino"),
    ("get", "/v2/callsign/{callsign}", [], AIRCRAFT_FIELDS, "curl.sh"),
    ("get", "/v2/sqk/{squawk}", [], ["count", "ac"], "curl.sh"),
    ("get", "/v2/mil", [], ["count", "ac"], "curl.sh"),
    ("get", "/v2/me/location", [], ["location"], "near_me.py"),
    ("get", "/v2/overflights", ["lat", "lon", "dist", "from", "to", "max_alt_ft"],
     ["lat", "lon", "dist_km", "from", "to", "count", "truncated", "complete_until", "coverage", "overflights"],
     "overflights.py"),
]
NESTED = [  # schema name, fields used
    ("Aircraft", AIRCRAFT_FIELDS),
    ("Overflight", ["closest_time", "closest_km", "min_alt_ft", "callsigns", "r", "t", "source"]),
    ("Error", ["error", "help"]),
]
HEADERS = ["X-FIA-Plan", "X-FIA-Used-Month"]  # read by near.mjs


def resolve(spec, node):
    seen = 0
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/") or seen > 10:
            fail(f"cannot resolve {ref}")
        node = spec
        for part in ref[2:].split("/"):
            node = node[part]
        seen += 1
    return node


def check_spec(spec):
    paths = spec["paths"]
    for method, path, params, fields, users in USES:
        op = paths.get(path, {}).get(method)
        if op is None:
            fail(f"{method.upper()} {path}, used by {users}, is no longer in the spec")
        have = {p.get("name") for p in (resolve(spec, p) for p in op.get("parameters", []))}
        missing = [p for p in params if p not in have]
        if missing:
            fail(f"{path}: parameters {missing}, used by {users}, are no longer in the spec")
        content = resolve(spec, op.get("responses", {}).get("200", {})).get("content", {})
        schema = resolve(spec, content.get("application/json", {}).get("schema", {}))
        props = schema.get("properties", {})
        missing = [f for f in fields if f not in props]
        if missing:
            fail(f"{path}: response fields {missing}, used by {users}, are no longer in the spec")
    schemas = spec.get("components", {}).get("schemas", {})
    for name, fields in NESTED:
        props = schemas.get(name, {}).get("properties", {})
        missing = [f for f in fields if f not in props]
        if missing:
            fail(f"schema {name}: fields {missing}, used by the examples, are no longer in the spec")
    headers = spec.get("components", {}).get("headers", {})
    missing = [h for h in HEADERS if h not in headers]
    if missing:
        fail(f"response headers {missing}, read by near.mjs, are no longer in the spec")


def check_readme_endpoints(spec):
    """Every endpoint in the README's Endpoints table must exist in the spec."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Endpoints", 1)[-1].split("\n## ", 1)[0]
    templates = []
    for path, ops in spec["paths"].items():
        pattern = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$"
        templates.append((re.compile(pattern), path, set(ops)))
    checked = 0
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        for code in re.findall(r"`([^`]+)`", line.split("|")[1]):
            method, _, path = code.rpartition(" ")
            method = (method or "get").lower()
            path, _, query = path.partition("?")
            concrete = "/v2" + re.sub(r"\{[^}]+\}", "x", path)
            match = [t for t in templates if t[0].match(concrete)]
            if not match or method not in match[0][2]:
                fail(f"README Endpoints table: {code} is not in the spec")
            op = spec["paths"][match[0][1]][method]
            names = {resolve(spec, p).get("name") for p in op.get("parameters", [])}
            for q in filter(None, (kv.split("=")[0] for kv in query.split("&"))):
                if q not in names:
                    fail(f"README Endpoints table: parameter {q} of {code} is not in the spec")
            checked += 1
    if checked < 10:
        fail(f"README Endpoints table: only {checked} endpoints found, the table no longer parses")


# The examples' default radii must fit the Free plan, or a new user's first run is a 403.
RADII = [
    ("examples/python/quickstart.py", r"/dist/(\d+)\""),
    ("examples/curl.sh", r"fia /lat/[-\d.]+/lon/[-\d.]+/dist/(\d+)"),
    ("examples/python/near_me.py", r'"--radius", type=float, default=(\d+)'),
    ("examples/node/near.mjs", r"km = (\d+)\] ="),
    ("examples/esp32/planes-overhead/planes-overhead.ino", r"RADIUS_KM = (\d+);"),
    ("examples/python/cache_server.py", r'"AREA", "[-\d.]+,[-\d.]+,(\d+)"'),
]


def check_examples(spec, plans):
    free = next(p for p in plans if p["name"] == "Free")
    for path, pattern in RADII:
        m = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
        if not m:
            fail(f"{path}: cannot find its default radius ({pattern}); update RADII in scripts/sync.py")
        if free["radius_km"] is not None and int(m.group(1)) > free["radius_km"]:
            fail(f"{path}: default radius {m.group(1)} km is above the Free plan's {free['radius_km']} km")
    desc = spec["paths"]["/v2/overflights"]["get"].get("description", "")
    m = re.search(r"Free (\d+) km / (\d+) h", desc)
    if not m:
        fail("/v2/overflights: the spec no longer states the Free plan's radius and window")
    src = (ROOT / "examples/python/overflights.py").read_text(encoding="utf-8")
    d_km = re.search(r'"--km", type=float, default=(\d+)', src)
    d_h = re.search(r'"--hours", type=float, default=(\d+)', src)
    if not (d_km and d_h):
        fail("overflights.py: cannot find its defaults; update scripts/sync.py")
    if int(d_km.group(1)) > int(m.group(1)) or int(d_h.group(1)) > int(m.group(2)):
        fail(f"overflights.py: defaults {d_km.group(1)} km / {d_h.group(1)} h exceed Free {m.group(1)} km / {m.group(2)} h")


def check_coverage_endpoint():
    """curl.sh reads the keyless coverage endpoint, which is not in the spec: check it live."""
    try:
        data = json.loads(get("https://api.flyitalyadsb.com/api/coverage?lat=45.46&lon=9.19&radius=50",
                              "application/json"))
        ok = isinstance(data["last_24h"]["aircraft"], int) and "now" in data and "receivers" in data
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        fail("/api/coverage no longer has last_24h.aircraft, now and receivers (read by curl.sh)")


# ---------------------------------------------------------------- main

def spec_change(old_text, new_spec):
    try:
        old = json.loads(old_text)
    except ValueError:
        return "new"
    added = len(set(new_spec["paths"]) - set(old.get("paths", {})))
    removed = len(set(old.get("paths", {})) - set(new_spec["paths"]))
    parts = [f"+{added} path{'s' * (added != 1)}" if added else "",
             f"-{removed} path{'s' * (removed != 1)}" if removed else ""]
    return ", ".join(p for p in parts if p) or "text"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="write nothing; exit 1 if anything would change")
    ap.add_argument("--summary", help="write a one-line summary of the changes to this file")
    args = ap.parse_args()

    try:
        spec, spec_text = fetch_openapi()
        site_llms = get(SITE + "/llms.txt", "text/plain")
        plans, per_ip = live_plans()
        coverage = live_coverage(site_llms)
        receivers = live_receivers(spec, site_llms)

        check_spec(spec)
        check_readme_endpoints(spec)
        check_examples(spec, plans)
        check_coverage_endpoint()

        changes, writes = [], {}
        old_spec = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if spec_text != old_spec:
            changes.append(f"openapi.json ({spec_change(old_spec, spec)})")
            writes[OPENAPI_PATH] = spec_text
        for filename, blocks in render(plans, per_ip, coverage, receivers).items():
            path = ROOT / filename
            old = path.read_text(encoding="utf-8")
            new = replace_blocks(old, blocks, filename)
            if new != old:
                changed = [n for n in blocks if replace_blocks(old, {n: blocks[n]}, filename) != old]
                changes.append(f"{filename} {', '.join(changed)}")
                writes[path] = new
    except SyncError as e:
        print(f"sync failed, nothing written: {e}", file=sys.stderr)
        sys.exit(2)

    summary = "; ".join(changes) if changes else "no changes"
    print(f"plans: {[(p['name'], p['price_eur'], p['per_min'], p['per_month'], p['radius_km']) for p in plans]}")
    print(f"per-IP {per_ip}/min, receivers about {receivers}, coverage {coverage}")
    print(f"sync: {summary}")
    if args.summary:
        pathlib.Path(args.summary).write_text(summary + "\n", encoding="utf-8")
    if args.dry_run:
        sys.exit(1 if changes else 0)
    for path, text in writes.items():
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
