import sentry_sdk
from sentry_sdk.scrubber import EventScrubber
from sentry_sdk.types import Event, Hint

from convergence_games.app.exceptions import UserNotLoggedInError
from convergence_games.settings import SETTINGS

CONTROL_FLOW_EXCEPTIONS = (UserNotLoggedInError,)


def _before_send(event: Event, hint: Hint) -> Event | None:
    if "exc_info" in hint:
        exc_type = hint["exc_info"][0]  # pyright: ignore[reportAny]
        if exc_type is not None and issubclass(exc_type, CONTROL_FLOW_EXCEPTIONS):
            event["level"] = "warning"
    return event


def init_sentry() -> None:
    if not SETTINGS.SENTRY_ENABLE:
        return

    _ = sentry_sdk.init(
        dsn=SETTINGS.SENTRY_DSN,
        environment=SETTINGS.SENTRY_ENVIRONMENT,
        release=SETTINGS.RELEASE,
        send_default_pii=True,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        event_scrubber=EventScrubber(
            denylist=[],
            pii_denylist=[],
        ),
        before_send=_before_send,
    )
