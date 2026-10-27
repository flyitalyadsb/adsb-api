"""Offline tests for scripts/sync.py: it must parse what the site serves today and
refuse (SyncError, nothing written) anything it can't parse completely.

    python3 scripts/test_sync.py
"""

import copy
import json
import pathlib
import unittest

import sync

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "openapi" / "openapi.json").read_text(encoding="utf-8"))

TABLE = """<table><tr><th>Plan</th><th>Price (before tax)</th><th>Requests/minute</th>
<th>Requests/month</th><th>Maximum radius</th></tr>
<tr><td>Free</td><td>free</td><td>30</td><td>300,000</td><td>500 km</td></tr>
<tr><td>Starter</td><td>€9/month</td><td>60</td><td>1,000,000</td><td>1,000 km</td></tr>
<tr><td>Pro</td><td>€49/month</td><td>300</td><td>10,000,000</td><td>no limit</td></tr></table>"""


def page(html):
    sync._fetched.clear()
    sync._fetched["https://example.test/"] = html
    return sync.plans_from_page("https://example.test/")


class Plans(unittest.TestCase):
    def test_parses_the_live_layout(self):
        plans = page(TABLE)
        self.assertEqual([p["name"] for p in plans], ["Free", "Starter", "Pro"])
        self.assertEqual(plans[1], {"name": "Starter", "price_eur": 9, "per_min": 60,
                                    "per_month": 1_000_000, "radius_km": 1000})
        self.assertIsNone(plans[2]["radius_km"])

    def test_refuses_what_it_cannot_parse(self):
        broken = {
            "no table": "<p>plans moved</p>",
            "price": TABLE.replace("€9/month", "9 euro"),
            "radius": TABLE.replace("1,000 km", "1000 miles"),
            "number": TABLE.replace(">60<", ">sixty<"),
            "missing cell": TABLE.replace("<td>60</td>", ""),
            "tax wording": TABLE.replace("(before tax)", ""),
            "two tables": TABLE + TABLE,
            "no Free": TABLE.replace(">Free<", ">Hobby<"),
        }
        for what, html in broken.items():
            with self.subTest(what), self.assertRaises(sync.SyncError):
                page(html)


class Spec(unittest.TestCase):
    def test_current_spec_passes(self):
        sync.check_spec(SPEC)
        sync.check_readme_endpoints(SPEC)

    def test_missing_endpoint_parameter_or_field_fails(self):
        for change in (
            lambda s: s["paths"].pop("/v2/mil"),
            lambda s: s["paths"]["/v2/overflights"]["get"].update(parameters=[
                q for q in s["paths"]["/v2/overflights"]["get"]["parameters"] if q["name"] != "max_alt_ft"]),
            lambda s: s["components"]["schemas"]["Aircraft"]["properties"].pop("alt_baro"),
            lambda s: s["components"]["schemas"]["AircraftList"]["properties"].pop("ac"),
            lambda s: s["components"]["headers"].pop("X-FIA-Used-Month"),
        ):
            spec = copy.deepcopy(SPEC)
            change(spec)
            with self.assertRaises(sync.SyncError):
                sync.check_spec(spec)

    def test_readme_endpoint_missing_from_spec_fails(self):
        spec = copy.deepcopy(SPEC)
        spec["paths"].pop("/v2/profile/{icao}")
        with self.assertRaises(sync.SyncError):
            sync.check_readme_endpoints(spec)


class Blocks(unittest.TestCase):
    def test_block_and_inline_replacement_is_idempotent(self):
        text = "a <!-- sync:n:start -->x<!-- sync:n:end --> b\n<!-- sync:t:start -->\nold\n<!-- sync:t:end -->\n"
        blocks = {"n": "about 9", "t": "new\n"}
        once = sync.replace_blocks(text, blocks, "f")
        self.assertEqual(once, "a <!-- sync:n:start -->about 9<!-- sync:n:end --> b\n"
                               "<!-- sync:t:start -->\nnew\n<!-- sync:t:end -->\n")
        self.assertEqual(sync.replace_blocks(once, blocks, "f"), once)

    def test_missing_or_repeated_marker_fails(self):
        for text in ("no markers", "<!-- sync:t:start --><!-- sync:t:start --><!-- sync:t:end -->",
                     "<!-- sync:t:end --> <!-- sync:t:start -->"):
            with self.assertRaises(sync.SyncError):
                sync.replace_blocks(text, {"t": "x\n"}, "f")

    def test_repo_files_have_every_marker(self):
        rendered = sync.render(page(TABLE), 100, {"as_of": "October 2026", "us": "1", "de": "1", "uk": "1",
                                                  "eu": "1", "it": "1"}, "3,200")
        for filename, blocks in rendered.items():
            sync.replace_blocks((ROOT / filename).read_text(encoding="utf-8"), blocks, filename)


class Coverage(unittest.TestCase):
    LLMS = ("- Where the receivers are (October 2026, receivers that share a position): about 36% in the "
            "United States, 15% in Germany, 11% in the UK and Ireland, 16% in the rest of Europe; then Asia. "
            "Italy, where the project started in 2020, is about 3%.")

    def test_parses_and_refuses(self):
        self.assertEqual(sync.live_coverage(self.LLMS)["us"], "36")
        with self.assertRaises(sync.SyncError):
            sync.live_coverage(self.LLMS.replace("Germany", "DE"))


if __name__ == "__main__":
    unittest.main()
