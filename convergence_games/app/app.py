from __future__ import annotations

from litestar import Litestar

from convergence_games.app.request_type import Request

from .app_config.mock_authentication_middleware import mock_authentication_middleware
from .app_config.openapi_config import openapi_config
from .app_config.sqlalchemy_plugin import sqlalchemy_plugin
from .app_config.template_config import template_config
from .routers import routers

app = Litestar(
    route_handlers=routers,
    dependencies={},
    request_class=Request,
    middleware=[mock_authentication_middleware],
    plugins=[sqlalchemy_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    debug=True,
)
