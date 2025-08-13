from typing import cast

from litestar.response import Redirect
from litestar.router import Router
from litestar.types.callable_types import BeforeRequestHookHandler

from convergence_games.app.request_type import Request

from .debug import DebugController
from .editor_test import EditorTestController
from .email_auth import EmailAuthController
from .event_manager import EventManagerController
from .event_player import EventPlayerController
from .game import GameController
from .home import HomeController
from .misc_components import MiscComponentsController
from .my_submissions import MySubmissionsController
from .oauth import OAuthController
from .party import PartyController
from .profile import ProfileController
from .search import SearchController
from .settings import SettingsController
from .submit_game import SubmitGameController


async def before_request_handler(request: Request) -> Redirect | None:
    # If we're logged in BUT hasn't set up their profile yet, redirect to the profile setup page
    # To finish filling out their more info
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
    tags=["frontend"],
    route_handlers=[
        DebugController,
        EditorTestController,
        EmailAuthController,
        EventManagerController,
        EventPlayerController,
        GameController,
        HomeController,
        MiscComponentsController,
        MySubmissionsController,
        OAuthController,
        PartyController,
        ProfileController,
        SearchController,
        SettingsController,
        SubmitGameController,
    ],
    before_request=cast(BeforeRequestHookHandler, before_request_handler),
)
