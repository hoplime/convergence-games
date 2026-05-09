from litestar.types import ControllerRouterHandler

from convergence_games.domain import routers as domain_routers

from .api import router as api_router

routers: list[ControllerRouterHandler] = [api_router, *domain_routers]
