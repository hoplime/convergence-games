from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import UserLogin
from convergence_games.db.ocean import Sqid


@dataclass
class PostEmailSignInForm:
    email: str


@dataclass
class PostProfileEditForm:
    first_name: str
    last_name: str
    description: str | None = None
    over_18: Literal["on"] | None = None

    @property
    def is_over_18(self) -> bool:
        return self.over_18 is not None


async def render_profile(
    request: Request,
    transaction: AsyncSession,
) -> Template:
    if request.user is None:
        return HTMXBlockTemplate(template_name="pages/register.html.jinja", block_name=request.htmx.target)

    if not request.user.is_profile_setup:
        return HTMXBlockTemplate(template_name="pages/more_info.html.jinja", block_name=request.htmx.target)

    user_logins: Sequence[UserLogin] = (
        (await transaction.execute(select(UserLogin).where(UserLogin.user_id == request.user.id))).scalars().all()
    )
    user_login_dict = {login.provider: login for login in user_logins}
    return HTMXBlockTemplate(
        template_name="pages/profile.html.jinja",
        block_name=request.htmx.target,
        context={"user_logins": user_login_dict},
    )


class ProfileController(Controller):
    @get(path="/email_sign_in")
    async def get_email_sign_in(self, request: Request, linking_account_sqid: Sqid | None = None) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/email_sign_in.html.jinja",
            block_name=request.htmx.target,
            context={
                "linking_account_sqid": linking_account_sqid,
            },
        )

    @post(path="/email_sign_in")
    async def post_email_sign_in(
        self,
        request: Request,
        data: Annotated[PostEmailSignInForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
        linking_account_sqid: Sqid | None = None,
    ) -> Template:
        request.app.emit(
            EVENT_EMAIL_SIGN_IN,
            email=data.email,
            linking_account_sqid=linking_account_sqid,
            transaction=transaction,
        )
        return HTMXBlockTemplate(
            template_name="components/forms/email_sign_in/VerifyCode.html.jinja",
            context={
                "email": data.email,
                "linking_account_sqid": linking_account_sqid,
            },
        )

    @get(path="/profile")
    async def get_profile(self, request: Request, transaction: AsyncSession) -> Template:
        return await render_profile(request, transaction)

    @post(path="/profile")
    async def post_profile(
        self,
        request: Request,
        data: Annotated[PostProfileEditForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Template:
        if request.user is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = request.user
        user.first_name = data.first_name
        user.last_name = data.last_name
        if data.description is not None:
            user.description = data.description
        user.over_18 = data.is_over_18
        transaction.add(user)

        return await render_profile(request, transaction)
