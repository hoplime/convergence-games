import time
import uuid
from typing import Any

import sentry_sdk
import structlog
from litestar.types import ASGIApp, Receive, Scope, Send

from convergence_games.logging.config import get_logger

_logger = get_logger("convergence_games.http")

_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_MAX_LEN = 64


class LoggingContextMiddleware:
    """ASGI middleware that binds per-request fields and emits a canonical log line.

    Binds `request_id`, `method`, and `path` into structlog contextvars so any
    log call within the request inherits them. Sets `request_id` on the active
    Sentry scope. Emits exactly one `http_request` log event per request with
    status, duration_ms, and any other fields downstream code bound during the
    request. Echoes `X-Request-ID` in the response headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        method = scope.get("method", "")
        path = scope.get("path", "")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=method,
            path=path,
        )

        if sentry_sdk.is_initialized():
            sentry_sdk.get_current_scope().set_tag("request_id", request_id)

        start = time.perf_counter()
        state: dict[str, Any] = {"status": 500, "response_bytes": 0}

        async def send_wrapper(message: Any) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message.get("status", 500)
                headers = list(message.get("headers") or [])
                # Replace any existing x-request-id header to avoid duplication.
                headers = [(k, v) for (k, v) in headers if k.lower() != _REQUEST_ID_HEADER]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            elif message["type"] == "http.response.body":
                body = message.get("body") or b""
                state["response_bytes"] += len(body)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _logger.exception(
                "http_request",
                status=500,
                duration_ms=duration_ms,
                response_bytes=state["response_bytes"],
                route=_route_name(scope),
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _logger.info(
                "http_request",
                status=state["status"],
                duration_ms=duration_ms,
                response_bytes=state["response_bytes"],
                route=_route_name(scope),
            )
        finally:
            structlog.contextvars.clear_contextvars()


def _resolve_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers") or []:
        if name.lower() == _REQUEST_ID_HEADER:
            try:
                decoded = value.decode("ascii", errors="ignore")[:_REQUEST_ID_MAX_LEN]
            except (AttributeError, UnicodeDecodeError):
                continue
            if decoded:
                return decoded
    return uuid.uuid4().hex


def _route_name(scope: Scope) -> str | None:
    handler = scope.get("route_handler")
    if handler is None:
        return None
    name = getattr(handler, "name", None)
    if name:
        return name
    fn = getattr(handler, "fn", None)
    if fn is not None:
        return getattr(fn, "__name__", None)
    return None
