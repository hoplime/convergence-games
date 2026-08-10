from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.datastructures import Cookie
from litestar.params import Body, RequestEncodingType
from litestar.plugins.htmx import ClientRedirect
from litestar.response import Redirect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserEventRole, UserLogin
from convergence_games.lib.auth import build_token_extras, jwt_cookie_auth
from convergence_games.lib.guards import user_guard
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template


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
    user_override: User | None = None,
) -> Template:
    user = user_override or request.user
    assert user is not None
    cookies = [Cookie(key="invalid-action-path", max_age=0)]

    if not user.is_profile_setup:
        return HTMXBlockTemplate(
            template_name="pages/more_info.html.jinja",
            block_name=request.htmx.target,
            cookies=cookies,
        )

    profile_user = user_override or (await transaction.execute(select(User).where(User.id == user.id))).scalar_one()

    user_logins: Sequence[UserLogin] = (
        (await transaction.execute(select(UserLogin).where(UserLogin.user_id == user.id))).scalars().all()
    )
    user_login_dict: dict[LoginProvider, list[UserLogin]] = {}
    for login in user_logins:
        if login.provider not in user_login_dict:
            user_login_dict[login.provider] = []
        user_login_dict[login.provider].append(login)
    return HTMXBlockTemplate(
        template_name="pages/profile.html.jinja",
        block_name=request.htmx.target,
        context={"profile_user": profile_user, "user_logins": user_login_dict},
        cookies=cookies,
    )


class ProfileController(Controller):
    @get(path="/profile")
    async def get_profile(
        self,
        request: Request,
        transaction: AsyncSession,
    ) -> Template | ClientRedirect | Redirect:
        if request.user is None:
            if request.htmx:
                return ClientRedirect("/sign-up")
            return Redirect(path="/sign-up")
        return await render_profile(request, transaction)

    @post(path="/profile", guards=[user_guard])
    async def post_profile(
        self,
        request: Request,
        data: Annotated[PostProfileEditForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Template:
        assert request.user is not None

        db_user = (await transaction.execute(select(User).where(User.id == request.user.id))).scalar_one()
        db_user.first_name = data.first_name.strip()
        db_user.last_name = data.last_name.strip()
        if data.description is not None:
            db_user.description = data.description
        db_user.over_18 = data.is_over_18
        await transaction.flush()

        event_roles = list(
            (await transaction.execute(select(UserEventRole).where(UserEventRole.user_id == db_user.id)))
            .scalars()
            .all()
        )
        login_response = jwt_cookie_auth.login(str(db_user.id), token_extras=build_token_extras(db_user, event_roles))

        response = await render_profile(request, transaction, user_override=db_user)
        for cookie in login_response.cookies:
            response.cookies.append(cookie)
        response.headers["HX-Refresh"] = "true"
        return response
