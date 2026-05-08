import logging
from typing import Any

import structlog

from convergence_games.logging import bind, bound, configure_logging, get_logger
from convergence_games.logging.processors import sentry_scope_processor


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    configure_logging()
    log = get_logger("test")
    log.info("after_double_configure")


def test_bound_contextvars_appear_in_event_dict(log_output: structlog.testing.LogCapture) -> None:
    log = get_logger("test")
    bind(request_id="abc")
    try:
        log.info("hello", value=42)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    matching = [e for e in log_output.entries if e["event"] == "hello"]
    assert len(matching) == 1
    assert matching[0]["request_id"] == "abc"
    assert matching[0]["value"] == 42


def test_bound_context_manager_scopes_fields(log_output: structlog.testing.LogCapture) -> None:
    log = get_logger("test")
    with bound(scope_field="x"):
        log.info("inside_scope")
    log.info("outside_scope")

    inside = next(e for e in log_output.entries if e["event"] == "inside_scope")
    outside = next(e for e in log_output.entries if e["event"] == "outside_scope")
    assert inside["scope_field"] == "x"
    assert "scope_field" not in outside


def test_sentry_scope_processor_handles_disabled_sentry() -> None:
    event_dict: dict[str, Any] = {"event": "x", "request_id": "abc"}
    result = sentry_scope_processor(None, "info", event_dict)
    assert result is event_dict
    assert result["request_id"] == "abc"


def test_stdlib_logger_routes_through_structlog_handler() -> None:
    """A plain stdlib logger.warning is routed through the structlog ProcessorFormatter."""
    root_handler = logging.getLogger().handlers[0]
    formatter = root_handler.formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
