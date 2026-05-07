from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.plugins.htmx import ClientRedirect
from litestar.response import Redirect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.app_config.jwt_cookie_auth import build_token_extras, jwt_cookie_auth
from convergence_games.app.common.auth import (
    AuthIntent,
    OAuthRedirectState,
    ProfileInfo,
    authorize_flow,
)
from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserEventRole, UserLogin
from convergence_games.db.ocean import Sqid, sink
from convergence_games.db.slugs import maybe_regenerate_slug
from convergence_games.utils.email import normalize_email


@dataclass
class PostEmailSignInForm:
    email: str


@dataclass
class PostAuthEmailForm:
    email: str
    redirect_path: str | None = None


@dataclass
class PostFromVerifiedEmailForm:
    state: str


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
    @get(path="/sign-up")
    async def get_sign_up(
        self,
        request: Request,
        invalid_action_path: Annotated[str, Parameter(cookie="invalid-action-path")] = "/profile",
        redirect_path: str | None = None,
    ) -> Template:
        cookies = [Cookie(key="invalid-action-path", max_age=0)]
        return HTMXBlockTemplate(
            template_name="pages/auth.html.jinja",
            block_name=request.htmx.target,
            headers={"HX-Replace-Url": "/sign-up"},
            context={
                "mode": "sign_up",
                "invalid_action_path": invalid_action_path,
                "redirect_path": redirect_path,
            },
            cookies=cookies,
        )

    @get(path="/sign-in")
    async def get_sign_in(
        self,
        request: Request,
        invalid_action_path: Annotated[str, Parameter(cookie="invalid-action-path")] = "/profile",
        redirect_path: str | None = None,
    ) -> Template:
        cookies = [Cookie(key="invalid-action-path", max_age=0)]
        return HTMXBlockTemplate(
            template_name="pages/auth.html.jinja",
            block_name=request.htmx.target,
            headers={"HX-Replace-Url": "/sign-in"},
            context={
                "mode": "sign_in",
                "invalid_action_path": invalid_action_path,
                "redirect_path": redirect_path,
            },
            cookies=cookies,
        )

    @post(path="/sign-up/email")
    async def post_sign_up_email(
        self,
        request: Request,
        data: Annotated[PostAuthEmailForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        email = normalize_email(data.email)
        state = OAuthRedirectState(redirect_path=data.redirect_path, mode=AuthIntent.SIGN_UP)
        request.app.emit(
            EVENT_EMAIL_SIGN_IN, email=email, state=state, session_factory=request.app.state.session_maker_class
        )
        return HTMXBlockTemplate(
            template_name="components/VerifyCode.html.jinja",
            context={"email": email, "state": state.encode(), "mode": "sign_up"},
        )

    @post(path="/sign-in/email")
    async def post_sign_in_email(
        self,
        request: Request,
        data: Annotated[PostAuthEmailForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Template:
        email = normalize_email(data.email)
        state = OAuthRedirectState(redirect_path=data.redirect_path, mode=AuthIntent.SIGN_IN)
        request.app.emit(
            EVENT_EMAIL_SIGN_IN, email=email, state=state, session_factory=request.app.state.session_maker_class
        )
        return HTMXBlockTemplate(
            template_name="components/VerifyCode.html.jinja",
            context={"email": email, "state": state.encode(), "mode": "sign_in"},
        )

    @post(path="/sign-up/from-verified-email")
    async def post_sign_up_from_verified_email(
        self,
        data: Annotated[PostFromVerifiedEmailForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Redirect:
        state = OAuthRedirectState.decode(data.state)
        if state.pending_verified_email is None:
            raise HTTPException(status_code=400, detail="State token missing verified email")
        email = normalize_email(state.pending_verified_email)
        return await authorize_flow(
            transaction=transaction,
            provider_name=LoginProvider.EMAIL,
            profile_info=ProfileInfo(user_id=email, user_email=email),
            intent=AuthIntent.SIGN_UP,
            redirect_path=state.redirect_path,
        )

    @get(path="/email-sign-in")
    async def get_email_sign_in(
        self, request: Request, linking_account_sqid: Sqid | None = None, redirect_path: str | None = None
    ) -> Template:
        linking_account_id = sink(linking_account_sqid) if linking_account_sqid is not None else None
        if linking_account_id is not None and (request.user is None or linking_account_id != request.user.id):
            raise HTTPException(detail="Invalid linking account ID", status_code=403)

        return HTMXBlockTemplate(
            template_name="pages/email_sign_in.html.jinja",
            block_name=request.htmx.target,
            headers={"HX-Replace-Url": "/email-sign-in"},
            context={
                "linking_account_sqid": linking_account_sqid,
                "redirect_path": redirect_path,
            },
        )

    @post(path="/email-sign-in")
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

        email = normalize_email(data.email)
        state = OAuthRedirectState(
            linking_account_sqid=linking_account_sqid,
            redirect_path=redirect_path,
        )
        request.app.emit(
            EVENT_EMAIL_SIGN_IN,
            email=email,
            state=state,
            session_factory=request.app.state.session_maker_class,
        )
        return HTMXBlockTemplate(
            template_name="components/VerifyCode.html.jinja",
            context={
                "email": email,
                "state": state.encode(),
            },
        )

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
        await maybe_regenerate_slug(
            transaction,
            db_user,
            source=f"{db_user.first_name} {db_user.last_name}".strip(),
            fallback="user",
        )
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
