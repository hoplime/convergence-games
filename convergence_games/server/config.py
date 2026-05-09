from litestar.config.compression import CompressionConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.plugins.htmx import HTMXConfig
from litestar.plugins.sqlalchemy import AlembicAsyncConfig, EngineConfig, SQLAlchemyAsyncConfig

from convergence_games.db.models import Base
from convergence_games.lib.template import template_config
from convergence_games.settings import SETTINGS

sqlalchemy = SQLAlchemyAsyncConfig(
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

compression = CompressionConfig(backend="brotli", exclude_opt_key="no_compression")

openapi = OpenAPIConfig(
    title="Convergence Games",
    version="0.1.0",
    path="/docs",
    render_plugins=[SwaggerRenderPlugin()],
)

htmx = HTMXConfig(set_request_class_globally=True)

template = template_config
