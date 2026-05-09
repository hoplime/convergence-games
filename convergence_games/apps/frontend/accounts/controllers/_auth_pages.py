from dataclasses import dataclass
from typing import Annotated

from litestar import Controller, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Redirect
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import LoginProvider
from convergence_games.lib.auth import (
    AuthIntent,
    OAuthRedirectState,
    ProfileInfo,
    authorize_flow,
)
from convergence_games.lib.events import EVENT_EMAIL_SIGN_IN
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template
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


class AuthPagesController(Controller):
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
        request.app.emit(EVENT_EMAIL_SIGN_IN, email=email, state=state, session_factory=request.app.state.session_maker_class)
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
        request.app.emit(EVENT_EMAIL_SIGN_IN, email=email, state=state, session_factory=request.app.state.session_maker_class)
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
