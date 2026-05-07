from collections.abc import Mapping
from typing import Any

import sentry_sdk
import structlog

_SENTRY_TAG_KEYS: frozenset[str] = frozenset(
    {
        "request_id",
        "user_id",
        "event_id",
        "game_id",
        "session_id",
        "route",
        "method",
        "path",
    }
)


def sentry_scope_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Copy a fixed set of bound contextvars onto the active Sentry scope.

    Runs as a structlog processor so every log call (issue or breadcrumb) carries
    the same fields the rendered log line does. Cheap to call when Sentry is
    disabled - sentry_sdk.set_tag is a no-op without an active hub.
    """
    if not sentry_sdk.is_initialized():
        return event_dict

    scope = sentry_sdk.get_current_scope()
    for key in _SENTRY_TAG_KEYS:
        value = event_dict.get(key)
        if value is not None:
            scope.set_tag(key, value)
    return event_dict


def drop_color_message(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Drop uvicorn's `color_message` key which duplicates `event` with ANSI colors."""
    event_dict.pop("color_message", None)
    return event_dict


def get_request_context() -> Mapping[str, Any]:
    """Return the currently bound structlog contextvars (for tests / debugging)."""
    return structlog.contextvars.get_contextvars()
