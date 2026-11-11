"""The client: one ``Client`` with a method per endpoint, standard library only."""

from __future__ import annotations

import gzip
import http.client
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, NamedTuple, Optional, Tuple, Union, overload

from ._version import __version__
from .errors import (
    ApiError,
    AuthError,
    NotFoundError,
    TransportError,
    error_from_response,
    header,
    retry_after,
)
from .models import (
    Aircraft,
    AircraftList,
    Events,
    HistoryDates,
    Limits,
    Overflights,
    Profile,
    Trace,
)

BASE_URL = "https://api.flyitalyadsb.com/v2"
#: The environment variable read when no key is passed.
API_KEY_ENV = "FLYITALYADSB_API_KEY"
#: Where to get a free key (self-serve, commercial use included).
SIGNUP_URL = "https://flyitalyadsb.com/data/api/?utm_source=python-client&utm_campaign=python-client#api-key"
#: The radius that covers the whole Earth from any point: ``world()``.
WORLD_RADIUS_KM = 20040
USER_AGENT = f"flyitalyadsb-python/{__version__}"
DEFAULT_TIMEOUT = 30.0

Number = Union[int, float]
#: A time: a ``datetime`` (naive = UTC), Unix seconds, or an ISO 8601 string.
TimeLike = Union[datetime, int, float, str]
Day = Union[date, str]

_ICAO = re.compile(r"[0-9a-fA-F]{6}")
_SQUAWK = re.compile(r"[0-7]{4}")
_TYPE = re.compile(r"[A-Za-z0-9]{2,4}")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: the key would go with it."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> Optional[urllib.request.Request]:
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


def _send(opener: urllib.request.OpenerDirector, method: str, url: str, headers: Mapping[str, str],
          body: Optional[bytes], timeout: float) -> Tuple[int, Dict[str, str], bytes]:
    """One HTTP request and its answer: (status, headers, decoded body), for error statuses too."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            status, resp_headers, raw = response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as e:
        status, resp_headers = e.code, dict(e.headers.items()) if e.headers else {}
        try:
            raw = e.read()
        except (OSError, http.client.HTTPException):
            raw = b""
        finally:
            e.close()
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        reason = getattr(e, "reason", None) or e
        raise TransportError(f"{method} {url.split('?')[0]}: {reason}") from e
    if (header(resp_headers, "Content-Encoding") or "").lower() == "gzip":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as e:
            raise TransportError(f"{method} {url.split('?')[0]}: unreadable gzip body") from e
    return status, resp_headers, raw


class _Answer(NamedTuple):
    data: Any
    headers: Dict[str, str]
    limits: Optional[Limits]


class Client:
    """A client for the FlyItalyADSB API (``https://api.flyitalyadsb.com/v2``).

    >>> from flyitalyadsb import Client
    >>> client = Client()  # the key from FLYITALYADSB_API_KEY
    >>> for a in client.near(51.47, -0.45, 25):  # 25 km around London Heathrow
    ...     print(a.callsign, a.registration, a.icao_type, a.altitude)

    Args:
        api_key: the key; by default the ``FLYITALYADSB_API_KEY`` environment variable.
            A free key, commercial use included: https://flyitalyadsb.com/data/api/#api-key
        base_url: the API's base URL.
        timeout: seconds to wait for each answer.
        user_agent: your app's name and version, e.g. ``"my-app/1.0"``; it goes before
            ``flyitalyadsb-python/<version>`` in the User-Agent header.
        max_retry_wait: on a 429 or 503 that carries ``Retry-After``, wait that long and
            try once more if it is at most this many seconds. 0 never retries.

    Every method raises ``PlanLimitError`` on a plan limit (403 or 429), ``AuthError``
    on a bad key (401), ``ApiError`` on other error answers and ``TransportError`` when
    there is no answer. ``limits`` holds the plan and usage of the last answer.
    """

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = BASE_URL,
                 timeout: float = DEFAULT_TIMEOUT, user_agent: Optional[str] = None,
                 max_retry_wait: float = 30.0) -> None:
        key = (api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")).strip()
        if not key:
            raise AuthError(f"no API key: pass Client(api_key=...) or set {API_KEY_ENV}. "
                            f"A free key (commercial use allowed) takes a minute: {SIGNUP_URL}")
        self._api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = f"{user_agent} {USER_AGENT}" if user_agent else USER_AGENT
        self.max_retry_wait = max_retry_wait
        #: The plan and usage reported by the last answer (``X-FIA-*`` headers).
        self.limits: Optional[Limits] = None
        self._opener = _opener()
        self._sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r})"

    # ------------------------------------------------------------------ live

    def near(self, lat: Number, lon: Number, radius_km: Number) -> AircraftList:
        """Every aircraft within ``radius_km`` kilometres of a point, anywhere on Earth.

        ``/lat/{lat}/lon/{lon}/dist/{km}``. The largest radius depends on the plan:
        500 km on Free, 1,000 km on Starter, no limit on Pro and Fleet. Above it the
        answer is ``PlanLimitError`` (``reason == "radius"``, not counted).
        """
        _check_point(lat, lon)
        _check_radius(radius_km, allow_zero=True)
        return self._aircraft_list(f"/lat/{_fmt(lat)}/lon/{_fmt(lon)}/dist/{_fmt(radius_km)}")

    def world(self) -> AircraftList:
        """Every aircraft the network sees now, worldwide, in one request.

        Needs the Pro or Fleet plan (``/lat/0/lon/0/dist/20040``); on Free and
        Starter it raises ``PlanLimitError`` with ``reason == "radius"``.
        """
        return self.near(0, 0, WORLD_RADIUS_KM)

    def by_icao(self, icao: str) -> Optional[Aircraft]:
        """One aircraft by 24-bit ICAO address (hex, either case); None if not seen now."""
        return self._one("/icao/", icao, "icao")

    def by_callsign(self, callsign: str) -> Optional[Aircraft]:
        """One aircraft by callsign (case and spaces ignored); None if not seen now."""
        return self._one("/callsign/", callsign, "callsign")

    def by_registration(self, registration: str) -> Optional[Aircraft]:
        """One aircraft by registration, e.g. ``"G-TTSI"``; None if not seen now."""
        return self._one("/reg/", registration, "registration")

    def military(self) -> AircraftList:
        """The military aircraft seen now, network-wide (``dbFlags`` bit 0)."""
        return self._aircraft_list("/mil")

    def pia(self) -> AircraftList:
        """The aircraft with a Privacy ICAO Address seen now (flagged, never hidden)."""
        return self._aircraft_list("/pia")

    def ladd(self) -> AircraftList:
        """The LADD aircraft seen now (flagged, never hidden)."""
        return self._aircraft_list("/ladd")

    def squawk(self, code: Union[str, int]) -> AircraftList:
        """The aircraft squawking a code, network-wide, e.g. ``7700``, ``7600``, ``7500``."""
        text = f"{code:04d}" if isinstance(code, int) and not isinstance(code, bool) else str(code).strip()
        if not _SQUAWK.fullmatch(text):
            raise ValueError(f"squawk must be 4 octal digits, e.g. 7700, not {code!r}")
        return self._aircraft_list(f"/sqk/{text}")

    def aircraft_type(self, designator: str) -> AircraftList:
        """The aircraft of an ICAO type designator seen now, e.g. ``"A320"``, ``"B738"``, ``"EC35"``."""
        text = str(designator).strip()
        if not _TYPE.fullmatch(text):
            raise ValueError(f"an ICAO type designator is 2-4 letters or digits, not {designator!r}")
        return self._aircraft_list(f"/type/{text}")

    # --------------------------------------------------------------- history

    @overload
    def history(self, icao: str) -> HistoryDates: ...

    @overload
    def history(self, icao: str, day: Day) -> Optional[Trace]: ...

    def history(self, icao: str, day: Optional[Day] = None) -> Union[HistoryDates, Optional[Trace]]:
        """Without ``day``: the UTC days with a track for one aircraft (``/history/{icao}``).

        With ``day`` (a ``date`` or ``"YYYY-MM-DD"``): that day's track
        (``/history/{icao}/{day}``), or None if there is none. Coverage: every day since
        2026-08-17, and 2022-2024 with gaps.
        """
        icao = _icao(icao)
        if day is None:
            answer = self._get(f"/history/{icao}")
            return HistoryDates.from_json(_mapping(answer.data), answer.limits)
        try:
            answer = self._get(f"/history/{icao}/{_day(day)}")
        except NotFoundError:
            return None
        return Trace.from_json(_mapping(answer.data), header(answer.headers, "X-History-Source"), answer.limits)

    def profile(self, icao: str) -> Optional[Profile]:
        """One aircraft in one request: identity, live status, history summary and links.

        None if the aircraft is not received now and has no history.
        """
        try:
            answer = self._get(f"/profile/{_icao(icao)}")
        except NotFoundError:
            return None
        return Profile.from_json(_mapping(answer.data), answer.limits)

    def overflights(self, lat: Number, lon: Number, radius_km: Number, start: TimeLike, end: TimeLike, *,
                    max_alt_ft: Optional[Number] = None, limit: Optional[int] = None) -> Overflights:
        """The aircraft whose track passed within ``radius_km`` of a point between two times.

        ``/overflights?lat=&lon=&dist=&from=&to=``: one entry per aircraft, with its closest
        point. Since 2026-08-17, up to about 10 minutes ago. Radius and window per plan:
        Starter 10 km / 6 h, Pro and Fleet 50 km / 24 h; not included on Free.

        Args:
            start, end: ``datetime`` (naive = UTC), Unix seconds or ISO 8601 strings.
            max_alt_ft: only the part of each track at or below this altitude.
            limit: at most this many aircraft (1-500, default 100).
        """
        _check_point(lat, lon)
        _check_radius(radius_km)
        answer = self._get("/overflights", {
            "lat": _fmt(lat), "lon": _fmt(lon), "dist": _fmt(radius_km),
            "from": _time(start), "to": _time(end),
            "max_alt_ft": None if max_alt_ft is None else _fmt(max_alt_ft),
            "limit": None if limit is None else str(int(limit)),
        })
        return Overflights.from_json(_mapping(answer.data), answer.limits)

    def events(self, lat: Number, lon: Number, radius_km: Number, *, since: Optional[TimeLike] = None,
               until: Optional[TimeLike] = None, kinds: Union[str, Iterable[str], None] = None,
               limit: Optional[int] = None) -> Events:
        """Notable traffic recorded in an area: emergencies, military and "interesting" aircraft.

        ``/events?lat=&lon=&dist=``, newest first. By default the last 24 hours; at most
        7 days back. The plan's radius applies. Every plan.

        Args:
            since, until: ``datetime`` (naive = UTC), Unix seconds or ISO 8601 strings.
            kinds: any of ``"emergency"``, ``"military"``, ``"interesting"`` (default all).
            limit: at most this many events (1-500, default 100).
        """
        _check_point(lat, lon)
        _check_radius(radius_km)
        if kinds is not None and not isinstance(kinds, str):
            kinds = ",".join(kinds)
        answer = self._get("/events", {
            "lat": _fmt(lat), "lon": _fmt(lon), "dist": _fmt(radius_km),
            "since": None if since is None else _time(since),
            "until": None if until is None else _time(until),
            "kinds": kinds,
            "limit": None if limit is None else str(int(limit)),
        })
        return Events.from_json(_mapping(answer.data), answer.limits)

    # ---------------------------------------------------------------- other

    def request(self, method: str, path: str, params: Optional[Mapping[str, Any]] = None,
                body: Optional[Mapping[str, Any]] = None) -> Any:
        """Any other endpoint, e.g. ``request("GET", "/me/location")`` or the webhooks.

        ``path`` is relative to the base URL. Returns the parsed JSON; errors raise as
        in the other methods.
        """
        params = {k: v for k, v in (params or {}).items() if v is not None}
        return self._call(method.upper(), "/" + path.lstrip("/"), params, body).data

    # ------------------------------------------------------------- internals

    def _get(self, path: str, params: Optional[Mapping[str, Optional[str]]] = None) -> _Answer:
        return self._call("GET", path, {k: v for k, v in (params or {}).items() if v is not None})

    def _aircraft_list(self, path: str) -> AircraftList:
        answer = self._get(path)
        return AircraftList.from_json(_mapping(answer.data), answer.limits)

    def _one(self, prefix: str, value: str, what: str) -> Optional[Aircraft]:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{what} is empty")
        try:
            answer = self._get(prefix + urllib.parse.quote(text, safe=""))
        except NotFoundError:
            return None
        return Aircraft.from_json(_mapping(answer.data))

    def _call(self, method: str, path: str, params: Mapping[str, Any],
              body: Optional[Mapping[str, Any]] = None) -> _Answer:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "X-Api-Key": self._api_key,
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        retried = False
        while True:
            status, resp_headers, raw = _send(self._opener, method, url, headers, data, self.timeout)
            limits = Limits.from_headers(resp_headers)
            if limits is not None:
                self.limits = limits
            if 200 <= status < 300:
                return _Answer(_json(raw, method, path), resp_headers, limits)
            wait = retry_after(resp_headers)
            if status in (429, 503) and not retried and wait is not None and wait <= self.max_retry_wait:
                # At most one retry, and only when the API says when.
                retried = True
                self._sleep(wait)
                continue
            raise error_from_response(status, resp_headers, raw, limits)


#: Who the data is for: the ``audience`` codes of ``POST /v2/keys``.
AUDIENCES = ("just_me", "my_product_users", "internal_org", "research", "other")
#: Whether another flight data source is already in use and what role this one will have:
#: the ``other_source`` codes. ``none``: this is the first; ``switching``: it becomes the main
#: one; ``backup``: it is the backup; ``comparing``: still comparing sources.
OTHER_SOURCES = ("none", "switching", "backup", "comparing")
#: The ``found_via`` codes of an AI assistant: only with them is ``ai_prompt`` kept.
AI_FOUND_VIA = frozenset({"chatgpt", "claude", "perplexity", "gemini", "copilot", "other_ai"})


def _code(value: Optional[str], name: str, allowed: Tuple[str, ...]) -> Optional[str]:
    if value is None:
        return None
    code = str(value).strip().lower()
    if code not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}, not {value!r}")
    return code


def _short(value: Optional[str], name: str, limit: int) -> Optional[str]:
    text = (value or "").strip()
    if len(text) > limit:
        raise ValueError(f"{name} can be at most {limit} characters, not {len(text)}")
    return text or None


def request_key(email: str, found_via: str = "pypi", *, audience: Optional[str] = None,
                other_source: Optional[str] = None, audience_other: Optional[str] = None,
                other_source_name: Optional[str] = None, ai_prompt: Optional[str] = None,
                name: Optional[str] = None, use_case: Optional[str] = None, lang: str = "en",
                base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT,
                user_agent: Optional[str] = None) -> Dict[str, Any]:
    """Ask for a free API key by email (``POST /v2/keys``). Nothing calls this for you.

    The answer never contains the key: the address receives a one-time link, valid for
    7 days, that shows the key once. Use only an address its owner gave you for this.
    One free key per mailbox; asking again for the same address is how a lost key is
    replaced (the old one works until the new link is opened).

    Args:
        email: an address a person controls (temporary domains are refused).
        found_via: how you found FlyItalyADSB, one of chatgpt, claude, perplexity, gemini,
            copilot, other_ai, search, github, api_list, forum, word_of_mouth, feeder, pypi,
            other. Defaults to ``"pypi"`` (this package). An AI agent asking for its user
            passes the assistant it is.
        audience: who the data is for, one of :data:`AUDIENCES`: ``just_me``,
            ``my_product_users``, ``internal_org``, ``research``, ``other``. Accepted now and
            soon required by the API: pass it (an agent asks its user rather than guessing).
        other_source: whether you already use another flight data source and what role this
            one will have, one of :data:`OTHER_SOURCES`: ``none``, ``switching``, ``backup``,
            ``comparing``. Accepted now and soon required, like ``audience``.
        audience_other: with ``audience="other"``, what (up to 120 characters).
        other_source_name: with an ``other_source`` other than ``"none"``, which source (up to
            120 characters).
        ai_prompt: only when ``found_via`` is an AI assistant (:data:`AI_FOUND_VIA`): what was
            asked to it (up to 300 characters).
        name: your app, device or agent (up to 200 characters).
        use_case: what it is for (up to 500 characters).
        lang: language of the email, ``"en"`` or ``"it"``.

    Returns:
        The API's answer, e.g. ``{"status": "ok", "message": "check your email ..."}``.

    Raises:
        ValueError: an ``audience`` or ``other_source`` outside the codes above, a text that
            goes with another answer, or one that is too long. Nothing is sent then.
    """
    aud = _code(audience, "audience", AUDIENCES)
    src = _code(other_source, "other_source", OTHER_SOURCES)
    aud_other = _short(audience_other, "audience_other", 120)
    src_name = _short(other_source_name, "other_source_name", 120)
    prompt = _short(ai_prompt, "ai_prompt", 300)
    if aud_other and aud != "other":
        raise ValueError('audience_other goes with audience="other"')
    if src_name and src in (None, "none"):
        raise ValueError('other_source_name goes with an other_source other than "none"')
    if prompt and found_via.strip().lower() not in AI_FOUND_VIA:
        raise ValueError("ai_prompt goes with an AI assistant in found_via: " + ", ".join(sorted(AI_FOUND_VIA)))
    if aud is None or src is None:
        warnings.warn("request_key(): pass audience= and other_source=; the API will soon require them "
                      f"(audience: {', '.join(AUDIENCES)}; other_source: {', '.join(OTHER_SOURCES)})",
                      FutureWarning, stacklevel=2)
    payload: Dict[str, Any] = {"email": email, "found_via": found_via, "lang": lang}
    for key, value in (("audience", aud), ("audience_other", aud_other), ("other_source", src),
                       ("other_source_name", src_name), ("ai_prompt", prompt)):
        if value:
            payload[key] = value
    if name:
        payload["name"] = name
    if use_case:
        payload["use_case"] = use_case
    headers = {
        "User-Agent": f"{user_agent} {USER_AGENT}" if user_agent else USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    status, resp_headers, raw = _send(_opener(), "POST", base_url.rstrip("/") + "/keys", headers,
                                      json.dumps(payload).encode("utf-8"), timeout)
    if 200 <= status < 300:
        return _mapping(_json(raw, "POST", "/keys"))
    raise error_from_response(status, resp_headers, raw)


# ------------------------------------------------------------------ helpers

def _json(raw: bytes, method: str, path: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise TransportError(f"{method} {path}: the answer is not JSON: {raw[:120]!r}") from e


def _mapping(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ApiError(f"unexpected answer: a JSON object was expected, got {type(data).__name__}")
    return data


def _fmt(value: Number) -> str:
    """A number for a URL: no exponent, at most 6 decimals."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"a number was expected, not {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"a finite number was expected, not {value!r}")
    if float(value).is_integer():
        return str(int(value))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def _check_point(lat: Number, lon: Number) -> None:
    if not -90 <= float(lat) <= 90:
        raise ValueError(f"lat must be within -90..90, not {lat!r}")
    if not -180 <= float(lon) <= 180:
        raise ValueError(f"lon must be within -180..180, not {lon!r}")


def _check_radius(radius_km: Number, allow_zero: bool = False) -> None:
    value = float(radius_km)
    if not (value >= 0 if allow_zero else value > 0):
        raise ValueError(f"radius_km must be a positive number of kilometres, not {radius_km!r}")


def _icao(icao: str) -> str:
    text = str(icao).strip()
    if not _ICAO.fullmatch(text):
        raise ValueError(f"an ICAO address is 6 hex characters, e.g. 4ca7b5, not {icao!r}")
    return text.lower()


def _day(day: Day) -> str:
    if isinstance(day, datetime):
        if day.tzinfo is not None:
            day = day.astimezone(timezone.utc)
        return day.date().isoformat()
    if isinstance(day, date):
        return day.isoformat()
    text = str(day).strip()
    if not _DAY.fullmatch(text):
        raise ValueError(f"day must be a date or YYYY-MM-DD, not {day!r}")
    return text


def _time(value: TimeLike) -> str:
    """A time for the API: ISO 8601 in UTC, or Unix seconds."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="seconds") + "Z"
    if isinstance(value, bool):
        raise TypeError(f"a time was expected, not {value!r}")
    if isinstance(value, (int, float)):
        return _fmt(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise TypeError(f"a time is a datetime, Unix seconds or an ISO 8601 string, not {value!r}")
