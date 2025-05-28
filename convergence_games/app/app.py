from __future__ import annotations

from litestar import Litestar

from convergence_games.settings import SETTINGS

from .app_config import (
    compression_config,
    dependencies,
    exception_handlers,
    htmx_plugin,
    init_sentry,
    jwt_cookie_auth,
    openapi_config,
    sqlalchemy_plugin,
    template_config,
)
from .events import all_listeners
from .routers import routers

init_sentry()

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
    debug=SETTINGS.DEBUG,
)
