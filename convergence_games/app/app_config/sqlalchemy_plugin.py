from litestar.plugins.sqlalchemy import AlembicAsyncConfig, EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

config = SQLAlchemyAsyncConfig(
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
        script_location="convergence_games/migrations",
    ),
)
sqlalchemy_plugin = SQLAlchemyPlugin(config)
