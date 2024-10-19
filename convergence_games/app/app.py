from __future__ import annotations

from litestar import Litestar
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

config = SQLAlchemyAsyncConfig(
    connection_string=SETTINGS.DATABASE_URL.render_as_string(hide_password=False),
    create_all=True,
    metadata=Base.metadata,
)
plugin = SQLAlchemyPlugin(config)
app = Litestar(
    route_handlers=[],
    plugins=[plugin],
    openapi_config=OpenAPIConfig(
        title="Convergence Games",
        version="0.1.0",
        path="/docs",
        render_plugins=[SwaggerRenderPlugin()],
    ),
    debug=True,
)
