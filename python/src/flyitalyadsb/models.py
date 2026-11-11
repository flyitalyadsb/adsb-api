"""Typed results. Each keeps the JSON the API sent in ``raw``, with the API's own field names."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, NamedTuple, Optional, Union

JSON = Dict[str, Any]

#: An altitude in feet, the string ``"ground"``, or ``None`` when unknown.
Altitude = Union[float, str, None]

MILITARY = 1
INTERESTING = 2
PIA = 4
LADD = 8


def _str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _alt(value: Any) -> Altitude:
    return "ground" if value == "ground" else _num(value)


def _obj(value: Any) -> JSON:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: Any) -> List[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


class _Flags:
    """The ``dbFlags`` bits. The data is unfiltered: these aircraft are flagged, never removed."""

    db_flags: int

    @property
    def military(self) -> bool:
        return bool(self.db_flags & MILITARY)

    @property
    def interesting(self) -> bool:
        return bool(self.db_flags & INTERESTING)

    @property
    def pia(self) -> bool:
        """Privacy ICAO Address."""
        return bool(self.db_flags & PIA)

    @property
    def ladd(self) -> bool:
        """Limiting Aircraft Data Displayed programme."""
        return bool(self.db_flags & LADD)


@dataclass(frozen=True)
class Limits:
    """The key's plan and usage, from the ``X-FIA-*`` headers of a response."""

    plan: Optional[str] = None
    """``X-FIA-Plan``: free, feeder, starter, pro, fleet or enterprise."""
    limit_per_min: Optional[int] = None
    """``X-FIA-Limit-Per-Min``: the plan's requests per minute."""
    quota_month: Optional[int] = None
    """``X-FIA-Quota-Month``: the plan's requests per month."""
    used_month: Optional[int] = None
    """``X-FIA-Used-Month``: requests counted this month (the counter resets on the 1st)."""
    headers: Mapping[str, str] = field(default_factory=dict, compare=False)
    """Every ``X-FIA-*`` header as received."""

    @property
    def remaining_month(self) -> Optional[int]:
        if self.quota_month is None or self.used_month is None:
            return None
        return max(0, self.quota_month - self.used_month)

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> Optional[Limits]:
        """The limits in a response's headers, or ``None`` if it has no ``X-FIA-*`` header."""
        fia = {k: v for k, v in headers.items() if k.lower().startswith("x-fia-")}
        if not fia:
            return None
        lower = {k.lower(): v.strip() for k, v in fia.items()}

        def number(name: str) -> Optional[int]:
            try:
                return int(lower[name])
            except (KeyError, ValueError):
                return None

        return cls(
            plan=lower.get("x-fia-plan") or None,
            limit_per_min=number("x-fia-limit-per-min"),
            quota_month=number("x-fia-quota-month"),
            used_month=number("x-fia-used-month"),
            headers=fia,
        )


@dataclass(frozen=True)
class Aircraft(_Flags):
    """One aircraft, as a record of readsb's aircraft.json.

    The common fields are typed here; ``raw`` has every field the API sent, with its
    readsb name (``get("nav_altitude_mcp")``). Units: feet, knots, ft/min, degrees.
    """

    hex: str
    """24-bit ICAO address; a leading ``~`` marks a non-ICAO (e.g. TIS-B) address."""
    callsign: Optional[str]
    """``flight``, without the padding spaces."""
    registration: Optional[str]
    """``r``."""
    icao_type: Optional[str]
    """``t``: ICAO type designator, e.g. A20N."""
    description: Optional[str]
    """``desc``: type description, when present."""
    lat: Optional[float]
    lon: Optional[float]
    altitude: Altitude
    """``alt_baro``: barometric altitude in feet, or ``"ground"``."""
    geom_altitude: Optional[float]
    """``alt_geom``: geometric altitude in feet."""
    ground_speed: Optional[float]
    """``gs``: knots."""
    track: Optional[float]
    """True track, degrees."""
    vertical_rate: Optional[float]
    """``baro_rate`` (or ``geom_rate``), ft/min."""
    squawk: Optional[str]
    emergency: Optional[str]
    category: Optional[str]
    """Emitter category, e.g. A3; A7 is a rotorcraft."""
    source: Optional[str]
    """``type``: where the position comes from, e.g. adsb_icao, mlat, tisb_icao."""
    db_flags: int
    """``dbFlags``: bit 0 military, 1 interesting, 2 PIA, 3 LADD."""
    seen: Optional[float]
    """Seconds since the last message."""
    seen_pos: Optional[float]
    """Seconds since the last position."""
    raw: JSON = field(repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Aircraft:
        flight = _str(data.get("flight"))
        rate = _num(data.get("baro_rate"))
        return cls(
            hex=str(data.get("hex", "")),
            callsign=(flight.strip() or None) if flight else None,
            registration=_str(data.get("r")),
            icao_type=_str(data.get("t")),
            description=_str(data.get("desc")),
            lat=_num(data.get("lat")),
            lon=_num(data.get("lon")),
            altitude=_alt(data.get("alt_baro")),
            geom_altitude=_num(data.get("alt_geom")),
            ground_speed=_num(data.get("gs")),
            track=_num(data.get("track")),
            vertical_rate=rate if rate is not None else _num(data.get("geom_rate")),
            squawk=_str(data.get("squawk")),
            emergency=_str(data.get("emergency")),
            category=_str(data.get("category")),
            source=_str(data.get("type")),
            db_flags=_int(data.get("dbFlags")) or 0,
            seen=_num(data.get("seen")),
            seen_pos=_num(data.get("seen_pos")),
            raw=dict(data),
        )

    @property
    def on_ground(self) -> bool:
        return self.altitude == "ground"

    @property
    def from_mlat(self) -> bool:
        """The position was computed by the network's multilateration (MLAT)."""
        return self.source == "mlat"

    def get(self, key: str, default: Any = None) -> Any:
        """A field of the raw record, by its API name."""
        return self.raw.get(key, default)


@dataclass(frozen=True)
class AircraftList:
    """The aircraft of a radius, ``/mil``, ``/pia``, ``/ladd``, ``/sqk`` or ``/type`` answer.

    Iterate over it, index it or take its ``len()``.
    """

    now: Optional[float]
    """Server time, Unix seconds."""
    count: int
    aircraft: List[Aircraft] = field(repr=False)
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], limits: Optional[Limits] = None) -> AircraftList:
        ac = data.get("ac")
        aircraft = [Aircraft.from_json(a) for a in ac if isinstance(a, Mapping)] if isinstance(ac, list) else []
        count = _int(data.get("count"))
        return cls(
            now=_num(data.get("now")),
            count=count if count is not None else len(aircraft),
            aircraft=aircraft,
            limits=limits,
            raw=dict(data),
        )

    def __iter__(self) -> Iterator[Aircraft]:
        return iter(self.aircraft)

    def __len__(self) -> int:
        return len(self.aircraft)

    def __getitem__(self, index: int) -> Aircraft:
        return self.aircraft[index]


@dataclass(frozen=True)
class HistoryDates:
    """``/history/{icao}``: the UTC days with a recorded track for one aircraft."""

    icao: str
    dates: List[str]
    """``YYYY-MM-DD``, oldest first."""
    count: int
    archive_unavailable: bool
    """True when the archive could not be listed: only recent days are included."""
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], limits: Optional[Limits] = None) -> HistoryDates:
        dates = _strings(data.get("dates"))
        count = _int(data.get("count"))
        return cls(
            icao=str(data.get("icao", "")),
            dates=dates,
            count=count if count is not None else len(dates),
            archive_unavailable=bool(data.get("archive_unavailable")),
            limits=limits,
            raw=dict(data),
        )


class TracePoint(NamedTuple):
    """One point of a day's track."""

    time: float
    """Unix seconds."""
    lat: Optional[float]
    lon: Optional[float]
    altitude: Altitude
    """Feet, or ``"ground"``."""
    ground_speed: Optional[float]
    """Knots."""
    track: Optional[float]
    """Degrees."""


@dataclass(frozen=True)
class Trace:
    """``/history/{icao}/{date}``: one aircraft's track for one UTC day (readsb trace_full).

    ``points`` are the raw rows, ``positions()`` the first fields of each as ``TracePoint``.
    """

    icao: str
    timestamp: Optional[float]
    """Unix seconds; each point's first value is the seconds after it."""
    points: List[List[Any]] = field(repr=False)
    source: Optional[str]
    """The ``X-History-Source`` header: local, r2, live or store."""
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], source: Optional[str] = None,
                  limits: Optional[Limits] = None) -> Trace:
        trace = data.get("trace")
        points = [p for p in trace if isinstance(p, list)] if isinstance(trace, list) else []
        return cls(
            icao=str(data.get("icao", "")),
            timestamp=_num(data.get("timestamp")),
            points=points,
            source=source,
            limits=limits,
            raw=dict(data),
        )

    def positions(self) -> List[TracePoint]:
        base = self.timestamp or 0.0
        out = []
        for p in self.points:
            offset = _num(p[0]) if p else None
            if offset is None:
                continue
            cell = (p + [None] * 6)[:6]
            out.append(TracePoint(base + offset, _num(cell[1]), _num(cell[2]), _alt(cell[3]),
                                  _num(cell[4]), _num(cell[5])))
        return out


@dataclass(frozen=True)
class Profile:
    """``/profile/{icao}``: one aircraft's identity, live status and history summary.

    Never includes owner or operator names.
    """

    icao: str
    identity: JSON
    """registration, icao_type, type_description, year, db_flags and the decoded flags."""
    live: JSON
    """seen_now, and when it is received now: callsign, source, position, altitude, speed."""
    history: JSON
    """first_day, last_day, days_last_30, total_days."""
    links: JSON
    """map (the public map on this aircraft) and history."""
    photos: JSON
    """page: a link to a public photo page (no image in the API), or None with withheld."""
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], limits: Optional[Limits] = None) -> Profile:
        return cls(
            icao=str(data.get("icao", "")),
            identity=_obj(data.get("identity")),
            live=_obj(data.get("live")),
            history=_obj(data.get("history")),
            links=_obj(data.get("links")),
            photos=_obj(data.get("photos")),
            limits=limits,
            raw=dict(data),
        )

    @property
    def registration(self) -> Optional[str]:
        return _str(self.identity.get("registration"))

    @property
    def icao_type(self) -> Optional[str]:
        return _str(self.identity.get("icao_type"))

    @property
    def type_description(self) -> Optional[str]:
        return _str(self.identity.get("type_description"))

    @property
    def db_flags(self) -> int:
        return _int(self.identity.get("db_flags")) or 0

    @property
    def military(self) -> bool:
        return bool(self.db_flags & MILITARY)

    @property
    def seen_now(self) -> bool:
        return bool(self.live.get("seen_now"))

    @property
    def first_day(self) -> Optional[str]:
        return _str(self.history.get("first_day"))

    @property
    def last_day(self) -> Optional[str]:
        return _str(self.history.get("last_day"))

    @property
    def map_url(self) -> Optional[str]:
        return _str(self.links.get("map"))


@dataclass(frozen=True)
class Overflight(_Flags):
    """One aircraft that passed within the radius, with its closest point."""

    icao: str
    registration: Optional[str]
    icao_type: Optional[str]
    description: Optional[str]
    db_flags: int
    callsigns: List[str]
    closest_time: Optional[str]
    """ISO 8601, UTC."""
    closest_km: Optional[float]
    closest_alt_ft: Altitude
    min_alt_ft: Altitude
    """The lowest altitude inside the circle: feet, ``"ground"`` or None."""
    source: Optional[str]
    """Source of the closest position: adsb, mlat, tisb or other."""
    positions: Optional[int]
    """Received positions inside the circle; 0 = interpolated between positions outside it."""
    raw: JSON = field(repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Overflight:
        return cls(
            icao=str(data.get("icao", "")),
            registration=_str(data.get("r")),
            icao_type=_str(data.get("t")),
            description=_str(data.get("desc")),
            db_flags=_int(data.get("dbFlags")) or 0,
            callsigns=_strings(data.get("callsigns")),
            closest_time=_str(data.get("closest_time")),
            closest_km=_num(data.get("closest_km")),
            closest_alt_ft=_alt(data.get("closest_alt_ft")),
            min_alt_ft=_alt(data.get("min_alt_ft")),
            source=_str(data.get("source")),
            positions=_int(data.get("positions")),
            raw=dict(data),
        )


@dataclass(frozen=True)
class Overflights:
    """``/overflights``: the aircraft that flew over a place between two times.

    When ``truncated`` is true, ask again with ``start=complete_until`` for the rest.
    ``gaps`` lists the periods that were not searched: there, no aircraft does not mean
    nothing flew over.
    """

    count: int
    truncated: bool
    complete_until: Optional[str]
    complete: Optional[bool]
    gaps: List[JSON]
    overflights: List[Overflight] = field(repr=False)
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], limits: Optional[Limits] = None) -> Overflights:
        items = data.get("overflights")
        flights = [Overflight.from_json(o) for o in items if isinstance(o, Mapping)] if isinstance(items, list) else []
        coverage = _obj(data.get("coverage"))
        gaps = coverage.get("gaps")
        complete = coverage.get("complete")
        count = _int(data.get("count"))
        return cls(
            count=count if count is not None else len(flights),
            truncated=bool(data.get("truncated")),
            complete_until=_str(data.get("complete_until")),
            complete=complete if isinstance(complete, bool) else None,
            gaps=[dict(g) for g in gaps if isinstance(g, Mapping)] if isinstance(gaps, list) else [],
            overflights=flights,
            limits=limits,
            raw=dict(data),
        )

    def __iter__(self) -> Iterator[Overflight]:
        return iter(self.overflights)

    def __len__(self) -> int:
        return len(self.overflights)

    def __getitem__(self, index: int) -> Overflight:
        return self.overflights[index]


@dataclass(frozen=True)
class Event:
    """A notable-traffic event: an emergency, a military or an "interesting" aircraft."""

    id: Optional[int]
    kind: Optional[str]
    """emergency, military or interesting."""
    reason: Optional[str]
    """Emergencies only: general, hijack, radio_failure, minimum_fuel, downed."""
    hex: str
    time: Optional[str]
    """ISO 8601, UTC: when the aircraft was seen entering the ~0.5 degree cell."""
    lat: Optional[float]
    lon: Optional[float]
    distance_km: Optional[float]
    callsign: Optional[str]
    registration: Optional[str]
    icao_type: Optional[str]
    squawk: Optional[str]
    source: Optional[str]
    map_url: Optional[str]
    raw: JSON = field(repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Event:
        flight = _str(data.get("flight"))
        return cls(
            id=_int(data.get("id")),
            kind=_str(data.get("kind")),
            reason=_str(data.get("reason")),
            hex=str(data.get("hex", "")),
            time=_str(data.get("time")),
            lat=_num(data.get("lat")),
            lon=_num(data.get("lon")),
            distance_km=_num(data.get("distance_km")),
            callsign=(flight.strip() or None) if flight else None,
            registration=_str(data.get("r")),
            icao_type=_str(data.get("t")),
            squawk=_str(data.get("squawk")),
            source=_str(data.get("source")),
            map_url=_str(data.get("map")),
            raw=dict(data),
        )


@dataclass(frozen=True)
class Events:
    """``/events``: notable traffic in an area, newest first."""

    count: int
    truncated: bool
    """More events matched than ``limit``."""
    since: Optional[str]
    until: Optional[str]
    events: List[Event] = field(repr=False)
    limits: Optional[Limits] = field(default=None, compare=False)
    raw: JSON = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: Mapping[str, Any], limits: Optional[Limits] = None) -> Events:
        items = data.get("events")
        events = [Event.from_json(e) for e in items if isinstance(e, Mapping)] if isinstance(items, list) else []
        count = _int(data.get("count"))
        return cls(
            count=count if count is not None else len(events),
            truncated=bool(data.get("truncated")),
            since=_str(data.get("since")),
            until=_str(data.get("until")),
            events=events,
            limits=limits,
            raw=dict(data),
        )

    def __iter__(self) -> Iterator[Event]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def __getitem__(self, index: int) -> Event:
        return self.events[index]
