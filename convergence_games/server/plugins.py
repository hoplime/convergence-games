from litestar.plugins.htmx import HTMXPlugin
from litestar.plugins.sqlalchemy import SQLAlchemyPlugin

from convergence_games.server import config

sqlalchemy = SQLAlchemyPlugin(config.sqlalchemy)
htmx = HTMXPlugin(config.htmx)
