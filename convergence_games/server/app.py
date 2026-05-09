from litestar import Litestar

from convergence_games.app.routers import routers
from convergence_games.lib.events import all_listeners
from convergence_games.settings import SETTINGS

from ._auth import jwt_cookie_auth
from ._dependencies import dependencies
from ._exceptions import exception_handlers
from ._plugins import compression_config, htmx_plugin, openapi_config, sqlalchemy_plugin
from ._sentry import init_sentry
from ._template import template_config

__all__ = ["app", "create_app"]


def create_app() -> Litestar:
    init_sentry()

    return Litestar(
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


app = create_app()
