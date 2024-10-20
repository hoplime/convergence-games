from litestar.types import ControllerRouterHandler

from .frontend import router as frontend_router

routers: list[ControllerRouterHandler] = [
    frontend_router,
]
