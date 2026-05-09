from collections.abc import AsyncGenerator

import sentry_sdk
from litestar.datastructures import Cookie
from litestar.di import Provide
from litestar.exceptions import ClientException
from litestar.response import Redirect
from litestar.status_codes import HTTP_409_CONFLICT
from sentry_sdk.scrubber import EventScrubber
from sentry_sdk.types import Event, Hint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import User
from convergence_games.lib.alerts import AlertError
from convergence_games.lib.exceptions import UserNotLoggedInError
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate
from convergence_games.lib.template import catalog
from convergence_games.services import ImageLoader, image_loader_from_settings
from convergence_games.settings import SETTINGS

# region Dependencies


async def provide_transaction(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    try:
        async with db_session.begin():
            yield db_session
    except IntegrityError as exc:
        raise ClientException(
            status_code=HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


async def provide_user(
    request: Request,
) -> User:
    if request.user is None:
        raise UserNotLoggedInError("User must be logged in to perform this action.")
    return request.user


async def provide_image_loader() -> ImageLoader:
    return image_loader_from_settings


dependencies = {
    "transaction": Provide(provide_transaction),
    "user": Provide(provide_user),
    "image_loader": Provide(provide_image_loader),
}


# region Exception handlers


def user_not_logged_in_handler(request: Request, exc: UserNotLoggedInError) -> Redirect:
    request_url_path = request.scope["path"]
    return Redirect(path="/profile", cookies=[Cookie(key="invalid-action-path", value=request_url_path, max_age=30)])


def alert_handler(request: Request, exc: AlertError) -> HTMXBlockTemplate:
    template_str = catalog.render(
        "ToastAlerts",
        alerts=exc.alerts,
        redirect_text=(exc.redirect_text or "Return Home") if not request.htmx else "",
        redirect_url=(exc.redirect_url or "/") if not request.htmx else "",
    )
    return HTMXBlockTemplate(
        template_str=template_str,
        re_target=request.query_params.get("alert-retarget", "#content"),
        re_swap="beforeend",
    )


exception_handlers = {
    UserNotLoggedInError: user_not_logged_in_handler,
    AlertError: alert_handler,
}


# region Sentry

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
