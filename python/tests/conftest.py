"""A local fake of the API: no test reaches the network."""

from __future__ import annotations

import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

Reply = Tuple[int, Dict[str, str], bytes]

FIA = {
    "X-FIA-Plan": "free",
    "X-FIA-Limit-Per-Min": "30",
    "X-FIA-Quota-Month": "300000",
    "X-FIA-Used-Month": "1234",
}


def reply(status: int = 200, body: Any = None, headers: Optional[Dict[str, str]] = None,
          raw: Optional[bytes] = None, compress: bool = False) -> Reply:
    data = raw if raw is not None else json.dumps(body).encode()
    h = {"Content-Type": "application/json", **FIA, **(headers or {})}
    if compress:
        data = gzip.compress(data)
        h["Content-Encoding"] = "gzip"
    return status, h, data


class FakeApi:
    """Routes ``(method, path with query)`` to queued replies and records every request."""

    def __init__(self) -> None:
        self.routes: Dict[Tuple[str, str], List[Reply]] = {}
        self.requests: List[Dict[str, Any]] = []
        self.url = ""

    def add(self, method: str, path: str, *replies: Reply) -> None:
        self.routes.setdefault((method, path), []).extend(replies)

    def take(self, method: str, path: str) -> Reply:
        queue = self.routes.get((method, path))
        if not queue:
            return reply(404, {"error": "no fake route for " + path})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    @property
    def last(self) -> Dict[str, Any]:
        return self.requests[-1]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    for name in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FLYITALYADSB_API_KEY", raising=False)
    fake = FakeApi()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            fake.requests.append({"method": self.command, "path": self.path,
                                  "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            status, headers, data = fake.take(self.command, self.path)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _handle

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}/v2"
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()
