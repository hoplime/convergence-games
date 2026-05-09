from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar import Litestar


def create_app() -> Litestar:
    from litestar import Litestar

    from convergence_games.app.routers import routers
    from convergence_games.lib.auth import jwt_cookie_auth
    from convergence_games.lib.events import all_listeners
    from convergence_games.lib.template import template_config
    from convergence_games.settings import SETTINGS

    from .core import dependencies, exception_handlers, init_sentry
    from .plugins import compression_config, htmx_plugin, openapi_config, sqlalchemy_plugin

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
