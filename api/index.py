"""Temporary deployment probe: minimal ASGI app, no app imports.

Used to distinguish a platform/routing failure from an application runtime
failure. Replaced by the real entrypoint in the next commit.
"""

import json


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    body = json.dumps({"ok": True, "probe": "minimal-asgi"}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
