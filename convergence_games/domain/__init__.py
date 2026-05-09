from typing import cast

from litestar.response import Redirect
from litestar.router import Router
from litestar.types import ControllerRouterHandler
from litestar.types.callable_types import BeforeRequestHookHandler

from convergence_games.lib.request_type import Request

from .accounts.controllers import EmailAuthController, OAuthController
from .admin.controllers import EventManagerController
from .debug.controllers import DebugController, EditorTestController
from .games.controllers import (
    EventGamesController,
    GameController,
    MiscComponentsController,
    SearchController,
    SubmitGameController,
)
from .player.controllers import PartyController, PlannerController, PreferencesController
from .public.controllers import HomeController
from .redirects.controllers import RedirectsController
from .system.controllers import favicon_router, health_check, static_files_router
from .user.controllers import MySubmissionsController, ProfileController, SettingsController


async def before_request_handler(request: Request) -> Redirect | None:
    if (
        request.method == "GET"
        and request.scope["path"] != "/profile"
        and request.user
        and not request.user.is_profile_setup
    ):
        return Redirect(path="/profile")


domain_router = Router(
    path="/",
    response_headers={"Vary": "hx-target"},
    include_in_schema=False,
    tags=["frontend"],
    route_handlers=[
        DebugController,
        EditorTestController,
        EmailAuthController,
        EventManagerController,
        EventGamesController,
        GameController,
        HomeController,
        MiscComponentsController,
        MySubmissionsController,
        OAuthController,
        PartyController,
        PlannerController,
        PreferencesController,
        ProfileController,
        RedirectsController,
        SearchController,
        SettingsController,
        SubmitGameController,
    ],
    before_request=cast(BeforeRequestHookHandler, before_request_handler),
)

system_router = Router(
    path="/",
    include_in_schema=False,
    tags=["system"],
    route_handlers=[
        favicon_router,
        static_files_router,
    ],
)

routers: list[ControllerRouterHandler] = [domain_router, system_router, health_check]
