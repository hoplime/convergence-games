from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Annotated

from litestar import Controller, get, post
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Redirect
from sqlalchemy import String, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.common.auth import (
    AccountAlreadyExistsError,
    AuthIntent,
    NoAccountForSignInError,
    OAuthRedirectState,
    ProfileInfo,
    authorize_flow,
    find_user_by_email,
)
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import UserEmailVerificationCode, UserLogin
from convergence_games.db.ocean import sink
from convergence_games.utils.email import normalize_email


async def login_with_email_and_code(
    email: str,
    code: str,
    transaction: AsyncSession,
    state: OAuthRedirectState,
    intent: AuthIntent | None = None,
) -> Redirect:
    email = normalize_email(email)
    user_email_verification_code = (
        await transaction.execute(
            select(UserEmailVerificationCode)
            .where(UserEmailVerificationCode.code == code)
            .where(UserEmailVerificationCode.email == email)
            .where(UserEmailVerificationCode.expires_at >= dt.datetime.now(tz=dt.timezone.utc))
        )
    ).scalar_one_or_none()

    if user_email_verification_code is None:
        raise HTTPException(status_code=401, detail="Invalid code or code expired")

    linking_account_id = sink(state.linking_account_sqid) if state.linking_account_sqid is not None else None
    if linking_account_id is not None:
        resolved_intent = AuthIntent.LINK
    elif intent is not None:
        resolved_intent = intent
    else:
        resolved_intent = AuthIntent.SIGN_IN

    profile_info = ProfileInfo(user_id=email, user_email=email)
    try:
        return await authorize_flow(
            transaction=transaction,
            provider_name=LoginProvider.EMAIL,
            profile_info=profile_info,
            intent=resolved_intent,
            linking_account_id=linking_account_id,
            redirect_path=state.redirect_path,
        )
    except NoAccountForSignInError:
        pass

    # No EMAIL login for this address. Look for a cross-provider match the email-code
    # owner can be safely linked into. Google verifies emails before issuing tokens, so
    # any GOOGLE login with a matching email is treated as proof both parties own it.
    matched_user = await find_user_by_email(transaction, email)
    if matched_user is not None:
        has_google_login = (
            await transaction.execute(
                select(UserLogin)
                .where(UserLogin.user_id == matched_user.id)
                .where(sql_cast(UserLogin.provider, String) == LoginProvider.GOOGLE.name)
                .where(func.lower(UserLogin.provider_email) == email)
            )
        ).scalar_one_or_none() is not None
        if has_google_login:
            return await authorize_flow(
                transaction=transaction,
                provider_name=LoginProvider.EMAIL,
                profile_info=profile_info,
                intent=AuthIntent.LINK,
                linking_account_id=matched_user.id,
                redirect_path=state.redirect_path,
            )

    # TODO(auth-flow-separation): remove this fallback once Phase 5 wires the
    # NoAccountFound UI; until then, preserve the prior auto-create behaviour
    # for the existing email-sign-in route.
    if intent is not None:
        raise NoAccountForSignInError(provider=LoginProvider.EMAIL, email=email)
    return await authorize_flow(
        transaction=transaction,
        provider_name=LoginProvider.EMAIL,
        profile_info=profile_info,
        intent=AuthIntent.SIGN_UP,
        linking_account_id=None,
        redirect_path=state.redirect_path,
    )


@dataclass
class PostVerifyCodeForm:
    email: str
    code: str
    mode: str | None = None


def _resolve_intent_from_mode(mode: str | None) -> AuthIntent | None:
    if mode is None:
        return None
    try:
        return AuthIntent(mode)
    except ValueError:
        return None


def _render_outcome_after_verify(
    outcome: NoAccountForSignInError | AccountAlreadyExistsError,
    fallback_email: str,
    state: OAuthRedirectState,
) -> Template:
    email = normalize_email(outcome.email or fallback_email)
    if isinstance(outcome, AccountAlreadyExistsError):
        return HTMXBlockTemplate(
            template_name="pages/account_exists.html.jinja",
            context={"email": email},
        )
    new_state = OAuthRedirectState(
        redirect_path=state.redirect_path,
        pending_verified_email=email,
    )
    return HTMXBlockTemplate(
        template_name="pages/no_account_found.html.jinja",
        context={"email": email, "state_token": new_state.encode()},
    )


class EmailAuthController(Controller):
    path = "/email_auth"

    @get(path="/magic_link")
    async def get_magic_link(
        self,
        magic_link_code: Annotated[str, Parameter(query="code")],
        transaction: AsyncSession,
        state_query: Annotated[str | None, Parameter(query="state")] = None,
    ) -> Redirect | Template:
        state = OAuthRedirectState.decode(state_query) if state_query is not None else OAuthRedirectState()
        code, email = UserEmailVerificationCode.decode_magic_link_code(magic_link_code)
        try:
            return await login_with_email_and_code(
                email, code, transaction, state=state, intent=AuthIntent.SIGN_IN
            )
        except (NoAccountForSignInError, AccountAlreadyExistsError) as outcome:
            return _render_outcome_after_verify(outcome, fallback_email=email, state=state)

    @post(path="/verify_code")
    async def post_verify_code(
        self,
        data: Annotated[PostVerifyCodeForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
        state_query: Annotated[str | None, Parameter(query="state")] = None,
    ) -> Redirect | Template:
        state = OAuthRedirectState.decode(state_query) if state_query is not None else OAuthRedirectState()
        intent = _resolve_intent_from_mode(data.mode) or state.mode
        try:
            return await login_with_email_and_code(
                data.email, data.code, transaction, state=state, intent=intent
            )
        except (NoAccountForSignInError, AccountAlreadyExistsError) as outcome:
            return _render_outcome_after_verify(outcome, fallback_email=data.email, state=state)
