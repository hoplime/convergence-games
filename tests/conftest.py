import logging
import os
from collections.abc import Iterator

import pytest

# Provide harmless defaults for env-driven Settings so test collection doesn't
# require a real .env file. Real values from the environment still win.
os.environ.setdefault("IMAGE_STORAGE_PATH", "/tmp/convergence_games_tests")
os.environ.setdefault("SENTRY_ENABLE", "false")
os.environ.setdefault("SIGNING_KEY", "By3l-4s0tyJ9W6muQQHhBguG7EsFv9BE-tHG8UsIliw=")
os.environ.setdefault("TOKEN_SECRET", "test-token-secret-32-chars-aaaaa")

import structlog  # noqa: E402

from convergence_games.logging.config import SHARED_PROCESSORS, configure_logging  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _configure_logging_for_tests() -> None:
    """Configure structlog once per test session and quiet root logger."""
    configure_logging()
    logging.getLogger().setLevel(logging.WARNING)


@pytest.fixture
def log_output() -> Iterator[structlog.testing.LogCapture]:
    """Capture structlog events emitted within the test for assertions.

    Restores the production-ish configuration after the test so other tests
    keep their handlers.
    """
    capture = structlog.testing.LogCapture()
    structlog.configure(processors=[*SHARED_PROCESSORS, capture])
    try:
        yield capture
    finally:
        configure_logging()
