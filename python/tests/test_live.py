"""One request to the real API, only when FLYITALYADSB_API_KEY is set (never in CI).

    FLYITALYADSB_API_KEY=... python -m pytest tests/test_live.py

It costs one request on that key: 25 km around Rome Fiumicino, within every plan.
"""

from __future__ import annotations

import os

import pytest

from flyitalyadsb import Client

pytestmark = pytest.mark.skipif(not os.environ.get("FLYITALYADSB_API_KEY"),
                                reason="set FLYITALYADSB_API_KEY to run the live smoke test")


def test_near_fiumicino() -> None:
    client = Client(user_agent="flyitalyadsb-python-tests")
    result = client.near(41.80, 12.25, 25)
    assert result.count == len(result) >= 0
    assert result.now is not None and result.now > 1_700_000_000
    assert client.limits is not None and client.limits.plan
    for a in result:
        assert a.hex
