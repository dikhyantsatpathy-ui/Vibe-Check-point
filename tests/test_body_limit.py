"""Global request-body cap: replaces the invalid FastAPI(max_body_size=...) kwarg."""
import asyncio

from app.body_limit import BodySizeLimitMiddleware, max_body_bytes


async def _ok_app(scope, receive, send):
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(len(body)).encode()})


def _call(app, headers, chunks):
    sent = []
    queue = list(chunks)

    async def receive():
        if not queue:
            return {"type": "http.disconnect"}
        c = queue.pop(0)
        return {"type": "http.request", "body": c, "more_body": bool(queue)}

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "headers": headers}
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def test_small_body_passes():
    app = BodySizeLimitMiddleware(_ok_app, max_bytes=100)
    status, body = _call(app, [(b"content-length", b"5")], [b"hello"])
    assert status == 200 and body == b"5"


def test_declared_content_length_over_limit_rejected_before_reading():
    app = BodySizeLimitMiddleware(_ok_app, max_bytes=100)
    status, _ = _call(app, [(b"content-length", b"101")], [b"x"])
    assert status == 413


def test_streamed_body_over_limit_rejected_even_without_content_length():
    app = BodySizeLimitMiddleware(_ok_app, max_bytes=100)
    status, body = _call(app, [], [b"a" * 60, b"b" * 60])
    assert status == 413 and b"too large" in body


def test_lying_content_length_is_still_capped():
    app = BodySizeLimitMiddleware(_ok_app, max_bytes=100)
    status, _ = _call(app, [(b"content-length", b"10")], [b"a" * 200])
    assert status == 413


def test_non_http_scopes_pass_through():
    called = []

    async def inner(scope, receive, send):
        called.append(scope["type"])

    asyncio.run(BodySizeLimitMiddleware(inner, max_bytes=1)({"type": "lifespan"}, None, None))
    assert called == ["lifespan"]


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1234")
    assert max_body_bytes() == 1234
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "garbage")
    assert max_body_bytes() == 50 * 1024 * 1024
