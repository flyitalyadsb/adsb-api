from __future__ import annotations

import json
import socket
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Tuple

import pytest

import flyitalyadsb
from flyitalyadsb import (
    ApiError,
    AuthError,
    Client,
    PlanLimitError,
    TransportError,
    request_key,
)

from conftest import FakeApi, reply

KEY = "test-key"

RADIUS: Dict[str, Any] = {
    "now": 1793114821.1,
    "count": 2,
    "total": 2,
    "ac": [
        {"hex": "40838b", "type": "adsb_icao", "flight": "BAW486L ", "r": "G-TTSI", "t": "A20N",
         "lat": 51.380496, "lon": -0.645676, "alt_baro": 5050, "alt_geom": 5200, "gs": 254.0,
         "track": 199.79, "baro_rate": 1344, "squawk": "2043", "category": "A3", "seen_pos": 0.4,
         "nav_qnh": 1013.2},
        {"hex": "33ffd1", "type": "mlat", "flight": "IAM4653 ", "r": "MM62179", "t": "C130",
         "alt_baro": "ground", "dbFlags": 1},
    ],
}


def client(api: FakeApi, **kwargs: object) -> Client:
    c = Client(KEY, base_url=api.url, **kwargs)  # type: ignore[arg-type]
    c._sleep = lambda seconds: None  # never really wait in tests
    return c


# ---------------------------------------------------------------------- basics

def test_near_sends_key_user_agent_and_parses(api: FakeApi) -> None:
    api.add("GET", "/v2/lat/51.47/lon/-0.45/dist/25", reply(body=RADIUS))
    result = client(api).near(51.47, -0.45, 25)

    headers = api.last["headers"]
    assert headers["x-api-key"] == KEY
    assert headers["user-agent"] == f"flyitalyadsb-python/{flyitalyadsb.__version__}"
    assert headers["accept"] == "application/json"

    assert result.count == 2 and len(result) == 2 and result.now == 1793114821.1
    a = result[0]
    assert (a.hex, a.callsign, a.registration, a.icao_type) == ("40838b", "BAW486L", "G-TTSI", "A20N")
    assert (a.altitude, a.ground_speed, a.vertical_rate, a.source) == (5050, 254.0, 1344, "adsb_icao")
    assert a.get("nav_qnh") == 1013.2 and a.raw["flight"] == "BAW486L "
    assert not a.military and not a.on_ground and not a.from_mlat
    mil = result[1]
    assert mil.military and mil.on_ground and mil.from_mlat and mil.altitude == "ground"
    assert [x.hex for x in result] == ["40838b", "33ffd1"]


def test_limits_from_headers(api: FakeApi) -> None:
    api.add("GET", "/v2/mil", reply(body={"now": 1, "count": 0, "ac": []},
                                       headers={"X-FIA-Plan": "pro", "X-FIA-Limit-Per-Min": "300",
                                                "X-FIA-Quota-Month": "10000000", "X-FIA-Used-Month": "42"}))
    c = client(api)
    assert c.limits is None
    result = c.military()
    for limits in (result.limits, c.limits):
        assert limits is not None
        assert (limits.plan, limits.limit_per_min, limits.quota_month, limits.used_month) == \
            ("pro", 300, 10_000_000, 42)
        assert limits.remaining_month == 10_000_000 - 42
        assert limits.headers["X-FIA-Plan"] == "pro"


def test_user_agent_of_the_app_goes_first(api: FakeApi) -> None:
    api.add("GET", "/v2/pia", reply(body={"now": 1, "count": 0, "ac": []}))
    client(api, user_agent="my-app/1.0").pia()
    assert api.last["headers"]["user-agent"] == f"my-app/1.0 flyitalyadsb-python/{flyitalyadsb.__version__}"


def test_paths_of_every_live_endpoint(api: FakeApi) -> None:
    empty = reply(body={"now": 1, "count": 0, "ac": []})
    c = client(api)
    calls: List[Tuple[Callable[[], object], str]] = [
        (lambda: c.world(), "/v2/lat/0/lon/0/dist/20040"),
        (lambda: c.near(-33.9461, 151.1772, 12.5), "/v2/lat/-33.9461/lon/151.1772/dist/12.5"),
        (lambda: c.military(), "/v2/mil"),
        (lambda: c.pia(), "/v2/pia"),
        (lambda: c.ladd(), "/v2/ladd"),
        (lambda: c.squawk(7700), "/v2/sqk/7700"),
        (lambda: c.squawk("0020"), "/v2/sqk/0020"),
        (lambda: c.squawk(20), "/v2/sqk/0020"),
        (lambda: c.aircraft_type("ec35"), "/v2/type/ec35"),
    ]
    for call, path in calls:
        api.add("GET", path, empty)
        call()
        assert api.last["path"] == path


def test_one_aircraft_and_not_seen_now(api: FakeApi) -> None:
    api.add("GET", "/v2/icao/40838b", reply(body=RADIUS["ac"][0]))
    api.add("GET", "/v2/callsign/BAW486L", reply(body=RADIUS["ac"][0]))
    api.add("GET", "/v2/reg/G-TTSI", reply(body=RADIUS["ac"][0]))
    api.add("GET", "/v2/icao/abcdef", reply(404, {"error": "not found"}))
    c = client(api)
    assert c.by_icao("40838b").registration == "G-TTSI"  # type: ignore[union-attr]
    assert c.by_callsign(" BAW486L ").hex == "40838b"  # type: ignore[union-attr]
    assert c.by_registration("G-TTSI").callsign == "BAW486L"  # type: ignore[union-attr]
    assert c.by_icao("abcdef") is None


def test_values_are_escaped_in_the_path(api: FakeApi) -> None:
    api.add("GET", "/v2/reg/A%2FB%20C", reply(404, {"error": "not found"}))
    assert client(api).by_registration("A/B C") is None
    assert api.last["path"] == "/v2/reg/A%2FB%20C"


def test_bad_arguments_never_reach_the_api(api: FakeApi) -> None:
    c = client(api)
    with pytest.raises(ValueError):
        c.squawk("7800")
    with pytest.raises(ValueError):
        c.aircraft_type("A-320")
    with pytest.raises(ValueError):
        c.history("xyz")
    with pytest.raises(ValueError):
        c.near(91, 0, 10)
    with pytest.raises(ValueError):
        c.near(0, 0, -1)
    with pytest.raises(ValueError):
        c.overflights(0, 0, 0, 1, 2)
    with pytest.raises(TypeError):
        c.near("45", 9, 10)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        c.by_callsign("  ")
    assert api.requests == []


# ------------------------------------------------------------------- history

def test_history_dates_and_a_gzip_trace(api: FakeApi) -> None:
    api.add("GET", "/v2/history/4ca7b5", reply(body={"icao": "4ca7b5", "count": 2,
                                                       "dates": ["2026-08-17", "2026-09-15"]}))
    trace = {"icao": "4ca7b5", "timestamp": 1757894400.0, "r": "EI-ABC",
             "trace": [[0, 45.1, 9.2, 3000, 210.5, 90.0, 0, 640], [12.5, 45.11, 9.25, "ground", None, None]]}
    api.add("GET", "/v2/history/4ca7b5/2026-09-15",
            reply(body=trace, headers={"X-History-Source": "r2"}, compress=True))
    api.add("GET", "/v2/history/4ca7b5/2026-09-16", reply(404, {"error": "not found"}))
    c = client(api)

    dates = c.history("4CA7B5")
    assert dates.dates == ["2026-08-17", "2026-09-15"] and dates.count == 2 and not dates.archive_unavailable

    day = c.history("4ca7b5", date(2026, 9, 15))
    assert api.last["headers"]["accept-encoding"] == "gzip"
    assert day is not None and day.source == "r2" and day.raw["r"] == "EI-ABC"
    points = day.positions()
    assert points[0] == (1757894400.0, 45.1, 9.2, 3000, 210.5, 90.0)
    assert points[1].altitude == "ground" and points[1].time == 1757894412.5

    late_evening_rome = datetime(2026, 9, 17, 0, 30, tzinfo=timezone(timedelta(hours=2)))
    assert c.history("4ca7b5", late_evening_rome) is None  # 2026-09-16 in UTC
    assert api.last["path"] == "/v2/history/4ca7b5/2026-09-16"


def test_profile(api: FakeApi) -> None:
    body = {"icao": "33ffd1",
            "identity": {"registration": "MM62179", "icao_type": "C130", "db_flags": 1, "military": True},
            "live": {"seen_now": True, "callsign": "IAM4653", "source": "mlat"},
            "history": {"first_day": "2022-05-01", "last_day": "2026-11-01", "days_last_30": 12},
            "links": {"map": "https://map.flyitalyadsb.com/?icao=33ffd1"},
            "photos": {"page": None, "withheld": None}}
    api.add("GET", "/v2/profile/33ffd1", reply(body=body))
    api.add("GET", "/v2/profile/000001", reply(404, {"error": "not found"}))
    c = client(api)
    p = c.profile("33ffd1")
    assert p is not None
    assert (p.registration, p.icao_type, p.military, p.seen_now) == ("MM62179", "C130", True, True)
    assert (p.first_day, p.last_day, p.map_url) == ("2022-05-01", "2026-11-01",
                                                    "https://map.flyitalyadsb.com/?icao=33ffd1")
    assert c.profile("000001") is None


def test_overflights_query_and_result(api: FakeApi) -> None:
    path = ("/v2/overflights?lat=45.4642&lon=9.19&dist=3&from=2026-10-21T08%3A00%3A00Z"
            "&to=2026-10-21T10%3A00%3A00Z&max_alt_ft=3000&limit=50")
    body = {"count": 1, "truncated": True, "complete_until": "2026-10-21T09:30:00Z",
            "coverage": {"complete": False, "gaps": [{"from": "2026-10-21T09:50:00Z",
                                                      "to": "2026-10-21T10:00:00Z", "reason": "not indexed yet"}]},
            "overflights": [{"icao": "4ca7b5", "r": "EI-ABC", "t": "B738", "dbFlags": 0, "callsigns": ["RYR42KD"],
                             "closest_time": "2026-10-21T08:41:07Z", "closest_km": 0.8, "min_alt_ft": 2100,
                             "source": "adsb", "positions": 4}]}
    api.add("GET", path, reply(body=body))
    start = datetime(2026, 10, 21, 10, 0, tzinfo=timezone(timedelta(hours=2)))  # 08:00 UTC
    result = client(api).overflights(45.4642, 9.19, 3, start, datetime(2026, 10, 21, 10, 0),
                                     max_alt_ft=3000, limit=50)
    assert api.last["path"] == path
    assert result.truncated and result.complete_until == "2026-10-21T09:30:00Z"
    assert result.complete is False and result.gaps[0]["reason"] == "not indexed yet"
    o = result[0]
    assert (o.icao, o.registration, o.callsigns, o.closest_km, o.min_alt_ft, o.source) == \
        ("4ca7b5", "EI-ABC", ["RYR42KD"], 0.8, 2100, "adsb")
    assert len(result) == 1 and list(result) == [o]


def test_overflights_take_unix_seconds_and_strings(api: FakeApi) -> None:
    path = "/v2/overflights?lat=1&lon=2&dist=5&from=1793000000&to=2026-10-21T10%3A00%3A00Z"
    api.add("GET", path, reply(body={"count": 0, "overflights": []}))
    client(api).overflights(1, 2, 5, 1793000000, "2026-10-21T10:00:00Z")
    assert api.last["path"] == path


def test_events(api: FakeApi) -> None:
    path = "/v2/events?lat=45.54&lon=10.22&dist=100&since=2026-10-21T12%3A00%3A00Z&kinds=emergency%2Cmilitary"
    body = {"since": "2026-10-21T12:00:00Z", "until": "2026-10-22T12:00:00Z", "count": 1, "truncated": False,
            "events": [{"id": 1842, "kind": "emergency", "reason": "general", "hex": "4ca7b5",
                        "time": "2026-10-22T09:41:07Z", "lat": 45.61, "lon": 10.33, "distance_km": 11.4,
                        "flight": "ABC123", "r": "I-ABCD", "t": "A320", "squawk": "7700", "source": "adsb_icao",
                        "map": "https://map.flyitalyadsb.com/?icao=4ca7b5"}]}
    api.add("GET", path, reply(body=body))
    events = client(api).events(45.54, 10.22, 100, since="2026-10-21T12:00:00Z", kinds=["emergency", "military"])
    assert api.last["path"] == path
    e = events[0]
    assert (e.id, e.kind, e.reason, e.callsign, e.squawk, e.distance_km) == \
        (1842, "emergency", "general", "ABC123", "7700", 11.4)
    assert e.map_url == "https://map.flyitalyadsb.com/?icao=4ca7b5"
    assert events.count == 1 and not events.truncated


def test_request_reaches_other_endpoints(api: FakeApi) -> None:
    api.add("GET", "/v2/me/location", reply(body={"location": None}))
    api.add("POST", "/v2/me/location", reply(body={"location": {"lat": 45.54, "lon": 10.22}}))
    c = client(api)
    assert c.request("GET", "me/location") == {"location": None}
    c.request("post", "/me/location", body={"lat": 45.54, "lon": 10.22})
    assert api.last["method"] == "POST"
    assert json.loads(api.last["body"]) == {"lat": 45.54, "lon": 10.22}
    assert api.last["headers"]["content-type"] == "application/json"


# ------------------------------------------------------------- limits and errors

def test_radius_above_the_plan(api: FakeApi) -> None:
    plans = "https://flyitalyadsb.com/data/api/?utm_source=api&utm_campaign=limit_radius#piani"
    api.add("GET", "/v2/lat/0/lon/0/dist/20040", reply(403, {
        "error": "dist above the free plan maximum of 500 km", "max_radius_km": 500, "plans": plans,
        "help": "https://flyitalyadsb.com/faq/#errore-403-raggio"}))
    c = client(api)
    with pytest.raises(PlanLimitError) as info:
        c.world()
    e = info.value
    assert (e.status, e.reason, e.max_radius_km, e.plans_url) == (403, "radius", 500, plans)
    assert e.help_url == "https://flyitalyadsb.com/faq/#errore-403-raggio"
    assert e.limits is not None and e.limits.plan == "free"
    assert "500 km" in str(e) and plans in str(e)
    assert len(api.requests) == 1  # a 403 is never retried


def test_monthly_quota_is_not_retried(api: FakeApi) -> None:
    api.add("GET", "/v2/mil", reply(429, {"error": "monthly request quota of this plan exhausted",
                                          "plan": "free", "quota_month": 300000, "resets": "2026-12-01",
                                          "help": "https://flyitalyadsb.com/faq/#errore-429"}))
    with pytest.raises(PlanLimitError) as info:
        client(api).military()
    e = info.value
    assert (e.reason, e.resets, e.plan, e.retry_after) == ("monthly_quota", "2026-12-01", "free", None)
    assert e.plans_url == flyitalyadsb.PLANS_URL  # the body had no plans link
    assert len(api.requests) == 1


def test_rate_limit_waits_retry_after_once(api: FakeApi) -> None:
    limited = reply(429, {"error": "rate limit exceeded for this API key", "limit_per_min": 30},
                    headers={"Retry-After": "2"})
    api.add("GET", "/v2/mil", limited, reply(body={"now": 1, "count": 0, "ac": []}))
    c = client(api)
    waits: List[float] = []
    c._sleep = waits.append
    assert c.military().count == 0
    assert waits == [2] and len(api.requests) == 2


def test_rate_limit_twice_raises_after_one_retry(api: FakeApi) -> None:
    limited = reply(429, {"error": "rate limit exceeded for this API key", "limit_per_min": 30},
                    headers={"Retry-After": "1"})
    api.add("GET", "/v2/mil", limited)
    with pytest.raises(PlanLimitError) as info:
        client(api).military()
    assert (info.value.reason, info.value.retry_after, info.value.limit_per_min) == ("rate_limit", 1, 30)
    assert len(api.requests) == 2


def test_no_retry_when_the_wait_is_too_long_or_disabled(api: FakeApi) -> None:
    api.add("GET", "/v2/mil", reply(429, {"error": "rate limit"}, headers={"Retry-After": "120"}))
    with pytest.raises(PlanLimitError):
        client(api).military()
    assert len(api.requests) == 1
    api.routes.clear()
    api.add("GET", "/v2/pia", reply(429, {"error": "rate limit"}, headers={"Retry-After": "1"}))
    with pytest.raises(PlanLimitError):
        client(api, max_retry_wait=0).pia()
    assert len(api.requests) == 2


def test_unavailable_with_retry_after_is_retried_once(api: FakeApi) -> None:
    api.add("GET", "/v2/overflights?lat=1&lon=2&dist=5&from=1&to=2",
            reply(503, {"error": "unavailable"}, headers={"Retry-After": "5"}),
            reply(body={"count": 0, "overflights": []}))
    assert client(api).overflights(1, 2, 5, 1, 2).count == 0
    assert len(api.requests) == 2


def test_overflights_limit_and_paid_plan(api: FakeApi) -> None:
    api.add("GET", "/v2/overflights?lat=1&lon=2&dist=40&from=1&to=2", reply(403, {
        "error": "dist above the free plan maximum of 10 km for overflights",
        "max_dist_km": 10, "max_window_hours": 6}))
    api.add("POST", "/v2/webhooks", reply(403, {
        "error": "webhooks are available on paid plans (Starter, Pro, Fleet)",
        "code": "paid-plan-required", "plan": "free", "plans": "https://example.test/plans"}))
    c = client(api)
    with pytest.raises(PlanLimitError) as info:
        c.overflights(1, 2, 40, 1, 2)
    assert info.value.reason == "overflights" and info.value.body["max_window_hours"] == 6
    with pytest.raises(PlanLimitError) as info:
        c.request("POST", "/webhooks", body={"url": "https://example.test/hook", "lat": 1, "lon": 2, "dist": 5})
    assert (info.value.reason, info.value.code, info.value.plans_url) == \
        ("paid_plan", "paid-plan-required", "https://example.test/plans")


def test_bad_key(api: FakeApi) -> None:
    api.add("GET", "/v2/mil", reply(401, {"error": "missing or invalid X-Api-Key",
                                          "help": "https://flyitalyadsb.com/faq/#errore-401"}))
    with pytest.raises(AuthError) as info:
        client(api).military()
    assert info.value.status == 401 and "invalid X-Api-Key" in str(info.value)
    assert KEY not in str(info.value) and KEY not in repr(info.value)


def test_html_from_the_edge_is_not_a_plan_limit(api: FakeApi) -> None:
    page = b"<!DOCTYPE html><html><title>Attention Required!</title></html>"
    api.add("GET", "/v2/mil", (403, {"Content-Type": "text/html"}, page))
    with pytest.raises(ApiError) as info:
        client(api).military()
    assert type(info.value) is ApiError
    assert "HTML page" in str(info.value) and "User-Agent" in str(info.value)


def test_other_errors(api: FakeApi) -> None:
    api.add("GET", "/v2/sqk/7700", reply(400, {"error": "squawk must be 4 octal digits"}))
    api.add("GET", "/v2/type/A320", (200, {"Content-Type": "text/plain"}, b"not json"))
    c = client(api)
    with pytest.raises(ApiError) as info:
        c.squawk(7700)
    assert info.value.status == 400 and info.value.message == "squawk must be 4 octal digits"
    with pytest.raises(TransportError):
        c.aircraft_type("A320")


def test_redirects_are_not_followed(api: FakeApi) -> None:
    api.add("GET", "/v2/mil", (302, {"Location": "https://elsewhere.example/v2/mil"}, b""))
    with pytest.raises(ApiError) as info:
        client(api).military()
    assert info.value.status == 302
    assert len(api.requests) == 1


def test_no_answer_is_a_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # nothing listens here once the socket is closed
    c = Client(KEY, base_url=f"http://127.0.0.1:{port}/v2", timeout=2)
    with pytest.raises(TransportError) as info:
        c.military()
    assert KEY not in str(info.value)


# ------------------------------------------------------------------- the key

def test_key_from_the_environment(api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLYITALYADSB_API_KEY", " env-key ")
    api.add("GET", "/v2/mil", reply(body={"now": 1, "count": 0, "ac": []}))
    c = Client(base_url=api.url)
    c.military()
    assert api.last["headers"]["x-api-key"] == "env-key"
    assert "env-key" not in repr(c)


def test_missing_key_points_to_the_signup(api: FakeApi) -> None:
    with pytest.raises(AuthError) as info:
        Client()
    assert "FLYITALYADSB_API_KEY" in str(info.value) and "api-key" in str(info.value)
    assert api.requests == []  # never asks for a key by itself


def test_request_key_posts_without_a_key(api: FakeApi) -> None:
    api.add("POST", "/v2/keys", reply(202, {"status": "ok", "message": "check your email for a link to your key"}))
    answer = request_key("you@example.com", audience="my_product_users", other_source="none", name="My app",
                         base_url=api.url)
    assert answer["status"] == "ok"
    sent = api.last
    assert "x-api-key" not in sent["headers"]
    assert json.loads(sent["body"]) == {"email": "you@example.com", "found_via": "pypi", "lang": "en",
                                        "audience": "my_product_users", "other_source": "none", "name": "My app"}


def test_request_key_sends_the_signup_answers(api: FakeApi) -> None:
    api.add("POST", "/v2/keys", reply(202, {"status": "ok"}))
    request_key("you@example.com", found_via="Claude", audience=" Other ", audience_other="A museum kiosk",
                other_source="backup", other_source_name="our own receiver", ai_prompt="free flight api with routes",
                base_url=api.url)
    assert json.loads(api.last["body"]) == {
        "email": "you@example.com", "found_via": "Claude", "lang": "en", "audience": "other",
        "audience_other": "A museum kiosk", "other_source": "backup", "other_source_name": "our own receiver",
        "ai_prompt": "free flight api with routes"}


def test_request_key_refuses_wrong_answers_before_sending(api: FakeApi) -> None:
    cases = [
        (dict(audience="me", other_source="none"), "audience must be one of just_me, my_product_users"),
        (dict(audience="just_me", other_source="yes"), "other_source must be one of none, switching, backup"),
        (dict(audience="just_me", audience_other="x", other_source="none"), 'audience_other goes with audience="other"'),
        (dict(audience="just_me", other_source="none", other_source_name="x"), "other_source_name goes with"),
        (dict(audience="just_me", other_source="none", ai_prompt="x"), "ai_prompt goes with an AI assistant"),
        (dict(audience="other", audience_other="x" * 121, other_source="none"), "at most 120 characters"),
    ]
    for kwargs, message in cases:
        with pytest.raises(ValueError, match=message):
            request_key("you@example.com", base_url=api.url, **kwargs)  # type: ignore[arg-type]
    assert api.requests == []


def test_request_key_warns_without_the_answers_the_api_will_require(api: FakeApi) -> None:
    api.add("POST", "/v2/keys", reply(202, {"status": "ok"}))
    with pytest.warns(FutureWarning, match="audience= and other_source="):
        request_key("you@example.com", base_url=api.url)
    assert json.loads(api.last["body"]) == {"email": "you@example.com", "found_via": "pypi", "lang": "en"}
    assert flyitalyadsb.AUDIENCES[-1] == "other" and "switching" in flyitalyadsb.OTHER_SOURCES


def test_request_key_errors(api: FakeApi) -> None:
    api.add("POST", "/v2/keys", reply(400, {"error": "found_via is required", "code": "found-via-required"}))
    with pytest.raises(ApiError) as info:
        request_key("you@example.com", found_via="tiktok", audience="just_me", other_source="none", base_url=api.url)
    assert info.value.code == "found-via-required"


def test_attribution_line() -> None:
    assert flyitalyadsb.ATTRIBUTION == "Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0"
