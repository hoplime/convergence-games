from typing import cast

from litestar.response import Redirect
from litestar.router import Router
from litestar.types.callable_types import BeforeRequestHookHandler

from convergence_games.lib.request_type import Request

from .accounts.controllers import AuthPagesController, EmailAuthController, OAuthController
from .admin.controllers import (
    AdminController,
    AllocationController,
    PlayersController,
    ScheduleController,
    SubmissionsController,
)
from .admin.controllers import SettingsController as EventSettingsController
from .debug.controllers import DebugController
from .games.controllers import (
    EventGamesController,
    GameController,
    MiscComponentsController,
    SearchController,
    SubmitGameController,
)
from .player.controllers import PartyController, PlannerController, PreferencesController
from .public.controllers import PublicController
from .redirects.controllers import RedirectsController
from .user.controllers import MySubmissionsController, ProfileController, SettingsController


async def before_request_handler(request: Request) -> Redirect | None:
    if (
        request.method == "GET"
        and request.scope["path"] != "/profile"
        and request.user
        and not request.user.is_profile_setup
    ):
        return Redirect(path="/profile")


router = Router(
    path="/",
    response_headers={"Vary": "hx-target"},
    include_in_schema=False,
    route_handlers=[
        AdminController,
        AllocationController,
        AuthPagesController,
        DebugController,
        EmailAuthController,
        EventGamesController,
        EventSettingsController,
        GameController,
        MiscComponentsController,
        MySubmissionsController,
        OAuthController,
        PartyController,
        PlannerController,
        PlayersController,
        PreferencesController,
        ProfileController,
        PublicController,
        RedirectsController,
        ScheduleController,
        SearchController,
        SettingsController,
        SubmissionsController,
        SubmitGameController,
    ],
    before_request=cast(BeforeRequestHookHandler, before_request_handler),
)
