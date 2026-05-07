from __future__ import annotations

from typing import Any

import sentry_sdk
from litestar import Litestar, Request
from litestar.datastructures import State

from convergence_games.logging import bind, configure_logging
from convergence_games.logging.middleware import LoggingContextMiddleware
from convergence_games.settings import SETTINGS

from .app_config import (
    compression_config,
    dependencies,
    exception_handlers,
    htmx_plugin,
    init_sentry,
    jwt_cookie_auth,
    logging_config,
    openapi_config,
    sqlalchemy_plugin,
    template_config,
)
from .events import all_listeners
from .routers import routers

configure_logging()
init_sentry()


async def bind_logging_user(request: Request[Any, Any, State]) -> None:
    """Bind the authenticated user_id onto the structlog context and Sentry scope."""
    user = request.scope.get("user")
    if user is None:
        return
    user_id = getattr(user, "id", None)
    if user_id is None:
        return
    bind(user_id=user_id)
    if sentry_sdk.is_initialized():
        sentry_sdk.set_user({"id": user_id, "email": getattr(user, "email", None)})


app = Litestar(
    route_handlers=routers,
    dependencies=dependencies,
    on_app_init=[jwt_cookie_auth.on_app_init],
    plugins=[sqlalchemy_plugin, htmx_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    compression_config=compression_config,
    exception_handlers=exception_handlers,  # type: ignore[assignment]
    listeners=all_listeners,
    middleware=[LoggingContextMiddleware],
    before_request=bind_logging_user,
    logging_config=logging_config,
    debug=SETTINGS.DEBUG,
)
