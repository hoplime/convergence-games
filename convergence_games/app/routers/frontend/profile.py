from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.common.auth import OAuthRedirectState
from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import UserLogin
from convergence_games.db.ocean import Sqid, sink


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
    invalid_action_path: str = "/profile",
) -> Template:
    cookies = [Cookie(key="invalid-action-path", max_age=0)]

    if request.user is None:
        return HTMXBlockTemplate(
            template_name="pages/register.html.jinja",
            block_name=request.htmx.target,
            context={"invalid_action_path": invalid_action_path},
            cookies=cookies,
        )

    if not request.user.is_profile_setup:
        return HTMXBlockTemplate(
            template_name="pages/more_info.html.jinja",
            block_name=request.htmx.target,
            cookies=cookies,
        )

    user_logins: Sequence[UserLogin] = (
        (await transaction.execute(select(UserLogin).where(UserLogin.user_id == request.user.id))).scalars().all()
    )
    user_login_dict = {login.provider: login for login in user_logins}
    return HTMXBlockTemplate(
        template_name="pages/profile.html.jinja",
        block_name=request.htmx.target,
        context={"user_logins": user_login_dict},
        cookies=cookies,
    )


class ProfileController(Controller):
    @get(path="/email_sign_in")
    async def get_email_sign_in(
        self, request: Request, linking_account_sqid: Sqid | None = None, redirect_path: str | None = None
    ) -> Template:
        linking_account_id = sink(linking_account_sqid) if linking_account_sqid is not None else None
        if linking_account_id is not None and (request.user is None or linking_account_id != request.user.id):
            raise HTTPException(detail="Invalid linking account ID", status_code=403)

        return HTMXBlockTemplate(
            template_name="pages/email_sign_in.html.jinja",
            block_name=request.htmx.target,
            context={
                "linking_account_sqid": linking_account_sqid,
                "redirect_path": redirect_path,
            },
        )

    @post(path="/email_sign_in")
    async def post_email_sign_in(
        self,
        request: Request,
        data: Annotated[PostEmailSignInForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
        linking_account_sqid: Sqid | None = None,
        redirect_path: str | None = None,
    ) -> Template:
        linking_account_id = sink(linking_account_sqid) if linking_account_sqid is not None else None
        if linking_account_id is not None and (request.user is None or linking_account_id != request.user.id):
            raise HTTPException(detail="Invalid linking account ID", status_code=403)

        state = OAuthRedirectState(
            linking_account_sqid=linking_account_sqid,
            redirect_path=redirect_path,
        )
        request.app.emit(
            EVENT_EMAIL_SIGN_IN,
            email=data.email,
            state=state,
            transaction=transaction,
        )
        return HTMXBlockTemplate(
            template_name="components/forms/email_sign_in/VerifyCode.html.jinja",
            context={
                "email": data.email,
                "is_linking": linking_account_sqid is not None,
                "state": state,
            },
        )

    @get(path="/profile")
    async def get_profile(
        self,
        request: Request,
        transaction: AsyncSession,
        invalid_action_path: Annotated[str, Parameter(cookie="invalid-action-path")] = "/profile",
    ) -> Template:
        return await render_profile(request, transaction, invalid_action_path=invalid_action_path)

    @post(path="/profile", guards=[user_guard])
    async def post_profile(
        self,
        request: Request,
        data: Annotated[PostProfileEditForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Template:
        assert request.user is not None

        user = request.user
        user.first_name = data.first_name
        user.last_name = data.last_name
        if data.description is not None:
            user.description = data.description
        user.over_18 = data.is_over_18
        transaction.add(user)

        return await render_profile(request, transaction)
