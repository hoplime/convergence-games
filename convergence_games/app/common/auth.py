from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cryptography.fernet import Fernet
from litestar.exceptions import HTTPException
from litestar.response import Redirect
from pydantic import BaseModel
from sqlalchemy import String, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.app_config.jwt_cookie_auth import (
    LEGACY_COOKIE_KEY,
    _issue_login_session,
    _make_clear_cookie,
)
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserEventRole, UserLogin
from convergence_games.db.ocean import Sqid
from convergence_games.settings import SETTINGS
from convergence_games.utils.email import normalize_email


class AuthIntent(StrEnum):
    SIGN_UP = "sign_up"
    SIGN_IN = "sign_in"
    LINK = "link"


@dataclass
class ProfileInfo:
    user_first_name: str | None = None
    user_last_name: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    user_profile_picture: str | None = None
    email_verified: bool = False


class AuthFlowOutcomeError(Exception):
    """Base class for non-happy-path branches authorize_flow surfaces to controllers."""


class AccountAlreadyExistsError(AuthFlowOutcomeError):
    def __init__(self, provider: LoginProvider, email: str | None) -> None:
        super().__init__(f"Account already exists for provider {provider.name}")
        self.provider = provider
        self.email = email


class NoAccountForSignInError(AuthFlowOutcomeError):
    def __init__(self, provider: LoginProvider, email: str | None) -> None:
        super().__init__(f"No account exists for provider {provider.name}")
        self.provider = provider
        self.email = email


class LinkConfirmationRequiredError(AuthFlowOutcomeError):
    def __init__(self, candidate_user_id: int, profile_info: ProfileInfo, provider: LoginProvider) -> None:
        super().__init__(f"Link confirmation required for {provider.name} -> user {candidate_user_id}")
        self.candidate_user_id = candidate_user_id
        self.profile_info = profile_info
        self.provider = provider


async def find_user_by_email(transaction: AsyncSession, email: str) -> User | None:
    """Find an existing user whose lowercased email matches across any provider.

    Prefers the user with an EMAIL login, then earliest user. Warns on ambiguous matches.
    """
    email_lower = normalize_email(email)
    rows = (
        (
            await transaction.execute(
                select(UserLogin)
                .where(
                    or_(
                        func.lower(UserLogin.provider_email) == email_lower,
                        (sql_cast(UserLogin.provider, String) == LoginProvider.EMAIL.name)
                        & (func.lower(UserLogin.provider_user_id) == email_lower),
                    )
                )
                .options(selectinload(UserLogin.user))
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return None

    users_by_id: dict[int, tuple[User, bool]] = {}
    for login in rows:
        user = login.user
        had_email = users_by_id.get(user.id, (user, False))[1]
        users_by_id[user.id] = (user, had_email or login.provider == LoginProvider.EMAIL)

    if len(users_by_id) > 1:
        print(f"find_user_by_email: ambiguous match for {email_lower!r}: user ids {sorted(users_by_id)}")

    sorted_users = sorted(
        users_by_id.values(),
        key=lambda entry: (not entry[1], entry[0].id),
    )
    return sorted_users[0][0]


async def _resolve_user_for_intent(
    transaction: AsyncSession,
    provider_name: LoginProvider,
    profile_info: ProfileInfo,
    intent: AuthIntent,
    user_login: UserLogin | None,
    linking_account_id: int | None,
) -> User:
    if intent == AuthIntent.LINK:
        if linking_account_id is None:
            raise HTTPException(status_code=400, detail="LINK intent requires linking_account_id")
        if user_login is not None:
            if user_login.user.id != linking_account_id:
                raise HTTPException(
                    status_code=403,
                    detail="Another account is already linked to this provider! Login to that account instead.",
                )
            return user_login.user
        user = (
            await transaction.execute(
                select(User).where(User.id == linking_account_id).options(selectinload(User.logins))
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.logins.append(
            UserLogin(
                provider=provider_name,
                provider_user_id=profile_info.user_id,
                provider_email=profile_info.user_email,
            )
        )
        return user
    if intent == AuthIntent.SIGN_UP:
        if user_login is not None:
            raise AccountAlreadyExistsError(provider=provider_name, email=profile_info.user_email)
        user = User(
            first_name=profile_info.user_first_name or "",
            last_name=profile_info.user_last_name or "",
            logins=[
                UserLogin(
                    provider=provider_name,
                    provider_user_id=profile_info.user_id,
                    provider_email=profile_info.user_email,
                )
            ],
        )
        transaction.add(user)
        return user
    if intent == AuthIntent.SIGN_IN:
        if user_login is None:
            raise NoAccountForSignInError(provider=provider_name, email=profile_info.user_email)
        return user_login.user
    raise HTTPException(status_code=500, detail=f"Unknown auth intent: {intent}")


async def authorize_flow(
    transaction: AsyncSession,
    provider_name: LoginProvider,
    profile_info: ProfileInfo,
    intent: AuthIntent,
    linking_account_id: int | None = None,
    redirect_path: str | None = None,
    extra_email_to_link: str | None = None,
    user_agent: str | None = None,
) -> Redirect:
    user_login = (
        await transaction.execute(
            select(UserLogin)
            .where(sql_cast(UserLogin.provider, String) == provider_name.name)
            .where(UserLogin.provider_user_id == profile_info.user_id)
            .options(selectinload(UserLogin.user))
        )
    ).scalar_one_or_none()

    user = await _resolve_user_for_intent(
        transaction, provider_name, profile_info, intent, user_login, linking_account_id
    )

    if extra_email_to_link is not None:
        await _attach_email_login_if_missing(transaction, user, extra_email_to_link)

    await transaction.flush()
    user_id = user.id

    event_roles = list(
        (await transaction.execute(select(UserEventRole).where(UserEventRole.user_id == user_id))).scalars().all()
    )
    access_cookie, refresh_cookie, _jti = await _issue_login_session(
        transaction, user, event_roles, user_agent=user_agent
    )
    redirect_path = redirect_path or "/profile"
    return Redirect(
        path=redirect_path,
        headers={"HX-Push-Url": redirect_path},
        cookies=[access_cookie, refresh_cookie, _make_clear_cookie(LEGACY_COOKIE_KEY)],
    )


async def _attach_email_login_if_missing(transaction: AsyncSession, user: User, email: str) -> None:
    """Add an EMAIL UserLogin to `user` for `email` if no matching login exists."""
    email_lower = normalize_email(email)
    existing = (
        await transaction.execute(
            select(UserLogin)
            .where(UserLogin.user_id == user.id)
            .where(sql_cast(UserLogin.provider, String) == LoginProvider.EMAIL.name)
            .where(func.lower(UserLogin.provider_user_id) == email_lower)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    transaction.add(
        UserLogin(
            user_id=user.id,
            provider=LoginProvider.EMAIL,
            provider_user_id=email_lower,
            provider_email=email_lower,
        )
    )


fernet = Fernet(SETTINGS.SIGNING_KEY)


class OAuthRedirectState(BaseModel):
    linking_account_sqid: Sqid | None = None
    redirect_path: str | None = None
    mode: AuthIntent | None = None
    pending_verified_email: str | None = None

    def encode(self) -> str:
        return fernet.encrypt(self.model_dump_json().encode()).decode()

    @classmethod
    def decode(cls, encoded: str) -> OAuthRedirectState:
        decoded = fernet.decrypt(encoded).decode()
        return cls.model_validate_json(decoded)


class PendingOAuthLink(BaseModel):
    """Signed payload describing an OAuth identity awaiting user-confirmed link to an existing user."""

    provider: LoginProvider
    provider_user_id: str
    provider_email: str | None = None
    user_first_name: str | None = None
    user_last_name: str | None = None
    user_profile_picture: str | None = None
    candidate_user_id: int
    redirect_path: str | None = None

    def encode(self) -> str:
        return fernet.encrypt(self.model_dump_json().encode()).decode()

    @classmethod
    def decode(cls, encoded: str) -> PendingOAuthLink:
        decoded = fernet.decrypt(encoded).decode()
        return cls.model_validate_json(decoded)
