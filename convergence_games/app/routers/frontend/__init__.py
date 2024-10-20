from litestar.router import Router

from .home import HomeController
from .static import static_files_router

router = Router(
    path="/",
    route_handlers=[
        static_files_router,
        HomeController,
    ],
)
