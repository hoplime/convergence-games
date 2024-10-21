from litestar.router import Router

from .favicon import favicon_router
from .home import HomeController
from .static import static_files_router

router = Router(
    path="/",
    route_handlers=[
        favicon_router,
        HomeController,
        static_files_router,
    ],
)
