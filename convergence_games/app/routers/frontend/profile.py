from dataclasses import dataclass
from typing import Annotated

from litestar import Controller, get, post
from litestar.params import Body, RequestEncodingType
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


@dataclass
class PostEmailSignInForm:
    email: str


class ProfileController(Controller):
    @get(path="/email_sign_in")
    async def get_email_sign_in(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/email_sign_in.html.jinja", block_name=request.htmx.target)

    @post(path="/email_sign_in")
    async def post_email_sign_in(
        self,
        request: Request,
        data: Annotated[PostEmailSignInForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Template:
        request.app.emit(EVENT_EMAIL_SIGN_IN, email=data.email, transaction=transaction)
        return HTMXBlockTemplate(
            template_name="components/forms/email_sign_in/VerifyCode.html.jinja", context={"email": data.email}
        )

    @get(path="/profile")
    async def get_profile(self, request: Request) -> Template:
        if request.user is None:
            return HTMXBlockTemplate(template_name="pages/register.html.jinja", block_name=request.htmx.target)
        return HTMXBlockTemplate(template_name="pages/profile.html.jinja", block_name=request.htmx.target)
