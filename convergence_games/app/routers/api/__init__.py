from litestar.router import Router

from convergence_games.settings import SETTINGS

from .debug import DebugController

route_handlers = []

if SETTINGS.DEBUG:
    route_handlers.append(DebugController)

router = Router(
    path="/api",
    tags=["api"],
    route_handlers=route_handlers,
)
