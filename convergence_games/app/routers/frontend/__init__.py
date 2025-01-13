from litestar.router import Router

from .auth import AuthController
from .favicon import favicon_router
from .games import GamesController
from .home import HomeController
from .profile import ProfileController
from .static import static_files_router

router = Router(
    path="/",
    response_headers={"Vary": "hx-target"},
    route_handlers=[
        AuthController,
        favicon_router,
        GamesController,
        HomeController,
        ProfileController,
        static_files_router,
    ],
)
