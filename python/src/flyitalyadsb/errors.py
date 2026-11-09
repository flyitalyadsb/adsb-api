"""Exceptions. Every one of them is a ``FlyItalyADSBError``."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

from .models import Limits

#: Plans and prices. A paid plan raises the limits of the key you already have.
PLANS_URL = "https://flyitalyadsb.com/data/api/?utm_source=python-client&utm_campaign=python-client#piani"
#: Limits, error codes and what to do about each.
LIMITS_DOCS_URL = "https://flyitalyadsb.com/data/api/docs/limits-and-errors/"


class FlyItalyADSBError(Exception):
    """Base class of the errors raised by this package."""


class TransportError(FlyItalyADSBError):
    """No usable HTTP answer: network error, timeout, TLS error, or an unreadable body."""


class ApiError(FlyItalyADSBError):
    """The API answered with an error status.

    ``status`` is the HTTP code, ``message`` the API's ``error`` text, ``body`` the JSON
    body (empty if it was not JSON), ``limits`` the ``X-FIA-*`` headers of the answer.
    """

    def __init__(self, message: str, *, status: Optional[int] = None,
                 body: Optional[Mapping[str, Any]] = None,
                 headers: Optional[Mapping[str, str]] = None,
                 limits: Optional[Limits] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.body: Dict[str, Any] = dict(body or {})
        self.headers: Dict[str, str] = dict(headers or {})
        self.limits = limits

    @property
    def code(self) -> Optional[str]:
        """The API's machine-readable ``code``, when the body has one."""
        code = self.body.get("code")
        return code if isinstance(code, str) else None

    @property
    def help_url(self) -> Optional[str]:
        """``help``: the FAQ answer for this error (on 401, 403 and 429)."""
        url = self.body.get("help")
        return url if isinstance(url, str) else None

    def __str__(self) -> str:
        text = self.message if self.status is None else f"HTTP {self.status}: {self.message}"
        if self.help_url:
            text += f" (help: {self.help_url})"
        return text


class AuthError(ApiError):
    """401: the API key is missing or invalid (a regenerated key replaces the old one)."""


class NotFoundError(ApiError):
    """404: e.g. the aircraft is not seen right now."""


class PlanLimitError(ApiError):
    """403 or 429: a limit of the key's plan. Refused requests are not counted or billed.

    ``reason`` says which limit:

    - ``"radius"`` (403): the radius is above the plan's maximum, see ``max_radius_km``.
      Shrink it, split the area, or upgrade: the whole world in one request needs Pro or Business.
    - ``"overflights"`` (403): the overflights radius or time window is above the plan's.
    - ``"paid_plan"`` (403): the feature needs a paid plan (webhooks).
    - ``"rate_limit"`` (429): too many requests per minute; wait ``retry_after`` seconds.
    - ``"monthly_quota"`` (429): the month's quota is used up until ``resets``.
    - ``"forbidden"`` (403): any other refusal; see ``message``.

    ``plans_url`` links to the plans.
    """

    def __init__(self, message: str, *, status: Optional[int] = None,
                 body: Optional[Mapping[str, Any]] = None,
                 headers: Optional[Mapping[str, str]] = None,
                 limits: Optional[Limits] = None) -> None:
        super().__init__(message, status=status, body=body, headers=headers, limits=limits)
        b = self.body
        if status == 429:
            self.reason = "monthly_quota" if ("resets" in b or "quota_month" in b) else "rate_limit"
        elif "max_radius_km" in b:
            self.reason = "radius"
        elif "max_dist_km" in b or "max_window_hours" in b:
            self.reason = "overflights"
        elif self.code == "paid-plan-required":
            self.reason = "paid_plan"
        else:
            self.reason = "forbidden"
        plans = b.get("plans")
        self.plans_url: str = plans if isinstance(plans, str) and plans else PLANS_URL
        self.retry_after: Optional[int] = retry_after(self.headers)
        self.max_radius_km: Optional[float] = _number(b.get("max_radius_km"))
        self.resets: Optional[str] = b.get("resets") if isinstance(b.get("resets"), str) else None
        per_min = b.get("limit_per_min", b.get("limit_per_min_per_ip"))
        self.limit_per_min: Optional[int] = per_min if isinstance(per_min, int) else None
        plan = b.get("plan")
        self.plan: Optional[str] = plan if isinstance(plan, str) else (limits.plan if limits else None)

    def __str__(self) -> str:
        text = super().__str__()
        if self.retry_after is not None:
            text += f"; retry after {self.retry_after} s"
        return f"{text}; plans: {self.plans_url}"


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def header(headers: Mapping[str, str], name: str) -> Optional[str]:
    """A header by name, ignoring case."""
    name = name.lower()
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def retry_after(headers: Mapping[str, str]) -> Optional[int]:
    """``Retry-After`` in seconds, or None if absent or not a number of seconds."""
    value = header(headers, "Retry-After")
    try:
        seconds = int(value.strip()) if value is not None else -1
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def error_from_response(status: int, headers: Mapping[str, str], raw: bytes,
                        limits: Optional[Limits] = None) -> ApiError:
    """The exception for an error answer."""
    try:
        body = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError):
        body = None
    if not isinstance(body, dict):
        head = raw[:4096].lower()
        if b"<html" in head or b"<!doctype" in head:
            message = ("an HTML page instead of JSON: the request was stopped before the API. "
                       "Send the X-Api-Key header and a User-Agent of your own "
                       f"(Client(user_agent='my-app/1.0')). Details: {LIMITS_DOCS_URL}")
        else:
            message = raw[:200].decode("utf-8", "replace").strip() or "empty answer"
        return ApiError(message, status=status, headers=headers, limits=limits)
    error = body.get("error")
    message = error if isinstance(error, str) and error else f"HTTP {status}"
    kwargs: Dict[str, Any] = {"status": status, "body": body, "headers": headers, "limits": limits}
    if status == 401:
        return AuthError(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status in (403, 429):
        return PlanLimitError(message, **kwargs)
    return ApiError(message, **kwargs)
