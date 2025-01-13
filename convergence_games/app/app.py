from __future__ import annotations

from litestar import Litestar

from convergence_games.settings import SETTINGS

from .app_config import (
    compression_config,
    htmx_plugin,
    mock_authentication_middleware,
    openapi_config,
    sqlalchemy_plugin,
    template_config,
)
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
