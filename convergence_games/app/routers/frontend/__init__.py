from typing import cast

from litestar.response import Redirect
from litestar.router import Router
from litestar.types.callable_types import BeforeRequestHookHandler

from convergence_games.app.request_type import Request

from .editor_test import EditorTestController
from .email_auth import EmailAuthController
from .event_profile import EventProfileController
from .home import HomeController
from .oauth import OAuthController
from .profile import ProfileController
from .settings import SettingsController
from .submit_game import SubmitGameController


async def before_request_handler(request: Request) -> Redirect | None:
    # If we're logged in BUT hasn't set up their profile yet, redirect to the profile setup page
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
        EditorTestController,
        EmailAuthController,
        EventProfileController,
        HomeController,
        OAuthController,
        ProfileController,
        SettingsController,
        SubmitGameController,
    ],
    before_request=cast(BeforeRequestHookHandler, before_request_handler),
)
