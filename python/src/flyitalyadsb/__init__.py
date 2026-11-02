"""Official Python client for the FlyItalyADSB ADS-B API.

Live aircraft positions as JSON for any point on Earth, from a community network of
ADS-B and MLAT receivers, plus history, overflights and notable-traffic events.
Commercial use is allowed on every plan, Free included. Standard library only.

    >>> from flyitalyadsb import Client
    >>> client = Client()  # reads FLYITALYADSB_API_KEY
    >>> for a in client.near(51.47, -0.45, 25):
    ...     print(a.callsign, a.registration, a.icao_type, a.altitude)

Docs: https://flyitalyadsb.com/en/data/api/docs/
Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0
"""

from ._version import __version__
from .client import (
    API_KEY_ENV,
    BASE_URL,
    SIGNUP_URL,
    USER_AGENT,
    WORLD_RADIUS_KM,
    Client,
    request_key,
)
from .errors import (
    LIMITS_DOCS_URL,
    PLANS_URL,
    ApiError,
    AuthError,
    FlyItalyADSBError,
    NotFoundError,
    PlanLimitError,
    TransportError,
)
from .models import (
    Aircraft,
    AircraftList,
    Altitude,
    Event,
    Events,
    HistoryDates,
    Limits,
    Overflight,
    Overflights,
    Profile,
    Trace,
    TracePoint,
)

#: The credit the data's licence asks for, where your users see the data.
ATTRIBUTION = "Flight data: FlyItalyADSB (flyitalyadsb.com), CC BY-SA 4.0"

__all__ = [
    "API_KEY_ENV",
    "ATTRIBUTION",
    "BASE_URL",
    "LIMITS_DOCS_URL",
    "PLANS_URL",
    "SIGNUP_URL",
    "USER_AGENT",
    "WORLD_RADIUS_KM",
    "Aircraft",
    "AircraftList",
    "Altitude",
    "ApiError",
    "AuthError",
    "Client",
    "Event",
    "Events",
    "FlyItalyADSBError",
    "HistoryDates",
    "Limits",
    "NotFoundError",
    "Overflight",
    "Overflights",
    "PlanLimitError",
    "Profile",
    "Trace",
    "TracePoint",
    "TransportError",
    "__version__",
    "request_key",
]
