from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

from convergence_games.db.models import Base
from convergence_games.settings import SETTINGS

config = SQLAlchemyAsyncConfig(
    connection_string=SETTINGS.DATABASE_URL.render_as_string(hide_password=False),
    create_all=True,
    metadata=Base.metadata,
)
sqlalchemy_plugin = SQLAlchemyPlugin(config)
