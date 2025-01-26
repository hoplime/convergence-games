from litestar.types import ControllerRouterHandler

from .api import router as api_router
from .frontend import router as frontend_router

routers: list[ControllerRouterHandler] = [
    frontend_router,
    api_router,
]
