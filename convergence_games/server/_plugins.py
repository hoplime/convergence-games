from litestar.config.compression import CompressionConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.plugins.htmx import HTMXConfig, HTMXPlugin
from litestar.plugins.sqlalchemy import AlembicAsyncConfig, EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

__all__ = [
    "compression_config",
    "htmx_plugin",
    "openapi_config",
    "sqlalchemy_config",
    "sqlalchemy_plugin",
]

sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string=SETTINGS.DATABASE_URL.render_as_string(hide_password=False),
    create_all=False,
    metadata=Base.metadata,
    before_send_handler="autocommit",
    engine_config=EngineConfig(
        echo=SETTINGS.DATABASE_ECHO,
        pool_pre_ping=True,
        pool_recycle=SETTINGS.DATABASE_POOL_RECYCLE,
    ),
    alembic_config=AlembicAsyncConfig(
        script_location="convergence_games/db/migrations",
    ),
)
sqlalchemy_plugin = SQLAlchemyPlugin(sqlalchemy_config)

compression_config = CompressionConfig(backend="brotli", exclude_opt_key="no_compression")

openapi_config = OpenAPIConfig(
    title="Convergence Games",
    version="0.1.0",
    path="/docs",
    render_plugins=[SwaggerRenderPlugin()],
)

htmx_config = HTMXConfig(set_request_class_globally=True)
htmx_plugin = HTMXPlugin(htmx_config)
