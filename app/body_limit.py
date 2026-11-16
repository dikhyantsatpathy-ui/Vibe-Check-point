"""Global request-body size cap (defence in depth).

FastAPI() has no `max_body_size` option; passing one is silently ignored by
some versions and raises TypeError on others (it crashed the Vercel function
at import). This pure-ASGI middleware provides the intended behaviour:

* A declared Content-Length above the limit is rejected immediately (413).
* A body that streams past the limit (chunked / lying Content-Length) is cut
  off with 413 as soon as the cap is crossed.

Per-endpoint caps (8 MB documents, 15 MB ML uploads) still apply on top.
"""
from __future__ import annotations

import json
import os

DEFAULT_MAX_BODY_BYTES = 50 * 1024 * 1024


def max_body_bytes() -> int:
    try:
        v = int(os.getenv("MAX_REQUEST_BODY_BYTES", "") or DEFAULT_MAX_BODY_BYTES)
        return v if v > 0 else DEFAULT_MAX_BODY_BYTES
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes if max_bytes is not None else max_body_bytes()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    break
                if declared > self.max_bytes:
                    await self._reject(send)
                    return
                break

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _TooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(send)

    async def _reject(self, send):
        body = json.dumps({"detail": "Request body too large."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
