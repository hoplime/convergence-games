import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST, DEFAULT_PII_DENYLIST, EventScrubber

from convergence_games.settings import SETTINGS


def init_sentry() -> None:
    """Initialize Sentry SDK."""
    if not SETTINGS.SENTRY_ENABLE:
        return

    sentry_sdk.init(
        dsn=SETTINGS.SENTRY_DSN,
        environment=SETTINGS.SENTRY_ENVIRONMENT,
        send_default_pii=True,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        event_scrubber=EventScrubber(
            denylist=[],
            pii_denylist=[],
        ),
    )
