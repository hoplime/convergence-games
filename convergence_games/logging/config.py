import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.contextvars import (
    bind_contextvars,
    bound_contextvars,
    unbind_contextvars,
)

from convergence_games.logging.processors import drop_color_message, sentry_scope_processor
from convergence_games.settings import SETTINGS

_configured: bool = False


SHARED_PROCESSORS: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    drop_color_message,
    sentry_scope_processor,
]


def _is_dev() -> bool:
    return SETTINGS.ENVIRONMENT == "development" or SETTINGS.DEBUG


def _build_renderer() -> structlog.types.Processor:
    if _is_dev():
        return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    return structlog.processors.JSONRenderer()


def configure_logging() -> None:
    """Configure structlog and stdlib logging once for the whole process.

    Safe to call multiple times - subsequent calls reapply the same configuration
    via logging.basicConfig(force=True). Litestar's StructLoggingConfig calls
    structlog.configure again at app startup with the same processor list, so
    the second pass is a no-op in effect.
    """
    global _configured

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *SHARED_PROCESSORS,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Disabled so reconfiguring at runtime (e.g. in tests) takes effect for
        # module-level cached loggers like the canonical-line emitter.
        cache_logger_on_first_use=False,
    )

    # ConsoleRenderer formats exc_info itself; JSONRenderer needs it pre-formatted.
    final_processors: list[structlog.types.Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]
    if not _is_dev():
        final_processors.append(structlog.processors.format_exc_info)
    final_processors.append(_build_renderer())

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=final_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if SETTINGS.DATABASE_ECHO else logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog BoundLogger.

    Pass __name__ from the call site so log records carry a useful logger name.
    """
    if name is None:
        return structlog.stdlib.get_logger()
    return structlog.stdlib.get_logger(name)


def bind(**fields: Any) -> None:
    """Bind fields onto the current structlog contextvars."""
    bind_contextvars(**fields)


def unbind(*keys: str) -> None:
    """Remove fields from the current structlog contextvars."""
    unbind_contextvars(*keys)


@contextmanager
def bound(**fields: Any) -> Iterator[None]:
    """Scoped contextvars binding - removes fields when the block exits."""
    with bound_contextvars(**fields):
        yield
