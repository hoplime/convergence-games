from litestar.router import Router

from .editor_test import EditorTestController
from .email_auth import EmailAuthController
from .favicon import favicon_router
from .games import GamesController
from .home import HomeController
from .oauth import OAuthController
from .profile import ProfileController
from .settings import SettingsController
from .static import static_files_router

router = Router(
    path="/",
    response_headers={"Vary": "hx-target"},
    include_in_schema=False,
    tags=["frontend"],
    route_handlers=[
        EditorTestController,
        EmailAuthController,
        favicon_router,
        GamesController,
        HomeController,
        OAuthController,
        ProfileController,
        SettingsController,
        static_files_router,
    ],
)
