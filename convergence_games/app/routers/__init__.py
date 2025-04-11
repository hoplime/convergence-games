from litestar.types import ControllerRouterHandler

from .api import router as api_router
from .frontend import router as frontend_router
from .static import router as static_router

routers: list[ControllerRouterHandler] = [
    api_router,
    frontend_router,
    static_router,
]
