from __future__ import annotations

from typing import TYPE_CHECKING, override

from litestar.plugins import InitPluginProtocol

from convergence_games.apps.api import router as api_router
from convergence_games.apps.frontend import router as frontend_router
from convergence_games.apps.system import router as system_router
from convergence_games.lib.auth import jwt_cookie_auth
from convergence_games.lib.deps import dependencies
from convergence_games.lib.events import all_listeners
from convergence_games.lib.exceptions import exception_handlers
from convergence_games.lib.sentry import init_sentry
from convergence_games.server import config, plugins
from convergence_games.settings import SETTINGS

if TYPE_CHECKING:
    from litestar.config.app import AppConfig


class ApplicationCore(InitPluginProtocol):
    @override
    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        init_sentry()

        app_config.debug = SETTINGS.DEBUG
        app_config = jwt_cookie_auth.on_app_init(app_config)

        app_config.plugins.extend([plugins.sqlalchemy, plugins.htmx])
        app_config.openapi_config = config.openapi
        app_config.compression_config = config.compression
        app_config.template_config = config.template

        app_config.route_handlers.extend([frontend_router, api_router, system_router])
        app_config.dependencies.update(dependencies)
        app_config.exception_handlers.update(exception_handlers)  # pyright: ignore[reportUnknownMemberType]
        app_config.listeners.extend(all_listeners)

        return app_config
