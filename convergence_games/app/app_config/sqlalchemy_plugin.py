from litestar.plugins.sqlalchemy import EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

config = SQLAlchemyAsyncConfig(
    connection_string=SETTINGS.DATABASE_URL.render_as_string(hide_password=False),
    create_all=True,
    metadata=Base.metadata,
    before_send_handler="autocommit",
    engine_config=EngineConfig(
        echo=SETTINGS.DATABASE_ECHO,
    ),
)
sqlalchemy_plugin = SQLAlchemyPlugin(config)
