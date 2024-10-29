from litestar import Controller, get, post
from litestar.datastructures import Cookie

from convergence_games.app.constants import AUTH_COOKIE_NAME
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class ProfileController(Controller):
    response_headers = {"Vary": "hx-target"}

    @get(path="/profile")
    async def get_profile(self, request: Request) -> Template:
        if request.user is None:
            return HTMXBlockTemplate(template_name="pages/register.html.jinja", block_name=request.htmx.target)
        return HTMXBlockTemplate(template_name="pages/profile.html.jinja", block_name=request.htmx.target)

    @get(path="/givemeaprofile/{user_id:int}")
    async def get_givemeaprofile(self, user_id: int) -> Template:
        response = HTMXBlockTemplate(
            template_name="pages/profile.html.jinja",
            cookies=[
                Cookie(
                    key=AUTH_COOKIE_NAME,
                    value=str(user_id),
                    max_age=60 * 60 * 24 * 365,
                    httponly=True,
                    secure=True,
                    samesite="strict",
                )
            ],
        )
        return response

    @post(path="/logout")
    async def post_logout(self, request: Request) -> Template:
        response = HTMXBlockTemplate(
            template_name="pages/profile.html.jinja",
            cookies=[
                Cookie(
                    key=AUTH_COOKIE_NAME,
                    value="",
                    max_age=0,
                    httponly=True,
                    secure=True,
                    samesite="strict",
                )
            ],
            block_name=request.htmx.target,
        )
        return response
