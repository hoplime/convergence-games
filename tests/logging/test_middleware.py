from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest
import structlog
from litestar.types import Receive, Scope, Send

from convergence_games.logging import bind
from convergence_games.logging.middleware import LoggingContextMiddleware


def _make_scope(method: str = "GET", path: str = "/test") -> Scope:
    raw: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
    }
    return cast(Scope, cast(object, raw))


async def _stub_app_factory(
    extra_action: Callable[[], None] | None = None,
    status: int = 200,
    body: bytes = b"hello",
) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if extra_action is not None:
            extra_action()
        start_msg: dict[str, Any] = {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain")],
        }
        body_msg: dict[str, Any] = {"type": "http.response.body", "body": body}
        await send(cast(Any, start_msg))
        await send(cast(Any, body_msg))

    return app


@pytest.mark.asyncio
async def test_canonical_log_line_emitted_with_context(log_output: structlog.testing.LogCapture) -> None:
    inner = await _stub_app_factory()
    middleware = LoggingContextMiddleware(inner)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await middleware(_make_scope(), cast(Receive, receive), cast(Send, send))

    canonical = [e for e in log_output.entries if e["event"] == "http_request"]
    assert len(canonical) == 1
    rec = canonical[0]
    assert rec["method"] == "GET"
    assert rec["path"] == "/test"
    assert rec["status"] == 200
    assert "request_id" in rec
    assert isinstance(rec["duration_ms"], float)
    assert rec["response_bytes"] == len(b"hello")

    start = next(m for m in sent if m["type"] == "http.response.start")
    headers = {k.lower(): v for k, v in start["headers"]}
    assert headers[b"x-request-id"].decode("ascii") == rec["request_id"]


@pytest.mark.asyncio
async def test_inbound_request_id_is_reused(log_output: structlog.testing.LogCapture) -> None:
    inner = await _stub_app_factory()
    middleware = LoggingContextMiddleware(inner)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = _make_scope()
    scope["headers"] = [(b"x-request-id", b"inbound-rid-1234")]
    await middleware(scope, cast(Receive, receive), cast(Send, send))

    canonical = next(e for e in log_output.entries if e["event"] == "http_request")
    assert canonical["request_id"] == "inbound-rid-1234"


@pytest.mark.asyncio
async def test_handler_bound_fields_appear_on_canonical_line(
    log_output: structlog.testing.LogCapture,
) -> None:
    def bind_inside_handler() -> None:
        bind(custom_field="from_handler")

    inner = await _stub_app_factory(extra_action=bind_inside_handler)
    middleware = LoggingContextMiddleware(inner)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        pass

    await middleware(_make_scope(), cast(Receive, receive), cast(Send, send))

    canonical = next(e for e in log_output.entries if e["event"] == "http_request")
    assert canonical["custom_field"] == "from_handler"


@pytest.mark.asyncio
async def test_contextvars_are_cleared_between_requests(
    log_output: structlog.testing.LogCapture,
) -> None:
    def bind_inside() -> None:
        bind(per_request="value")

    inner = await _stub_app_factory(extra_action=bind_inside)
    middleware = LoggingContextMiddleware(inner)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        pass

    await middleware(_make_scope(path="/first"), cast(Receive, receive), cast(Send, send))
    await middleware(_make_scope(path="/second"), cast(Receive, receive), cast(Send, send))

    assert structlog.contextvars.get_contextvars() == {}
    canonical = [e for e in log_output.entries if e["event"] == "http_request"]
    assert len(canonical) == 2
    assert {e["path"] for e in canonical} == {"/first", "/second"}


@pytest.mark.asyncio
async def test_exception_is_logged_then_reraised(log_output: structlog.testing.LogCapture) -> None:
    async def boom_app(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("boom")

    middleware = LoggingContextMiddleware(boom_app)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        pass

    with pytest.raises(RuntimeError, match="boom"):
        await middleware(_make_scope(), cast(Receive, receive), cast(Send, send))

    canonical = next(e for e in log_output.entries if e["event"] == "http_request")
    assert canonical["status"] == 500
