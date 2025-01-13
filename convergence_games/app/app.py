from __future__ import annotations

from litestar import Litestar

from convergence_games.settings import SETTINGS

from .app_config.compression_config import compression_config
from .app_config.htmx_plugin import htmx_plugin
from .app_config.mock_authentication_middleware import mock_authentication_middleware
from .app_config.openapi_config import openapi_config
from .app_config.sqlalchemy_plugin import sqlalchemy_plugin
from .app_config.template_config import template_config
from .routers import routers

app = Litestar(
    route_handlers=routers,
    dependencies={},
    middleware=[mock_authentication_middleware],
    plugins=[sqlalchemy_plugin, htmx_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    compression_config=compression_config,
    debug=SETTINGS.DEBUG,
)
