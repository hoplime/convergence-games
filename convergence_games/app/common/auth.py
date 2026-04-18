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

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserLogin
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
    ).scalars().all()

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


async def authorize_flow(
    transaction: AsyncSession,
    provider_name: LoginProvider,
    profile_info: ProfileInfo,
    intent: AuthIntent,
    linking_account_id: int | None = None,
    redirect_path: str | None = None,
) -> Redirect:
    user_login = (
        await transaction.execute(
            select(UserLogin)
            .where(sql_cast(UserLogin.provider, String) == provider_name.name)
            .where(UserLogin.provider_user_id == profile_info.user_id)
            .options(selectinload(UserLogin.user))
        )
    ).scalar_one_or_none()

    if intent == AuthIntent.LINK:
        if linking_account_id is None:
            raise HTTPException(status_code=400, detail="LINK intent requires linking_account_id")
        if user_login is not None:
            if user_login.user.id != linking_account_id:
                raise HTTPException(
                    status_code=403,
                    detail="Another account is already linked to this provider! Login to that account instead.",
                )
            user = user_login.user
        else:
            user = (
                await transaction.execute(select(User).where(User.id == linking_account_id))
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
    elif intent == AuthIntent.SIGN_UP:
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
    elif intent == AuthIntent.SIGN_IN:
        if user_login is None:
            raise NoAccountForSignInError(provider=provider_name, email=profile_info.user_email)
        user = user_login.user
    else:
        raise HTTPException(status_code=500, detail=f"Unknown auth intent: {intent}")

    await transaction.flush()
    user_id = user.id
    login = jwt_cookie_auth.login(str(user_id))
    redirect_path = redirect_path or "/profile"
    return Redirect(path=redirect_path, headers={"HX-Push-Url": redirect_path}, cookies=login.cookies)


fernet = Fernet(SETTINGS.SIGNING_KEY)


class OAuthRedirectState(BaseModel):
    linking_account_sqid: Sqid | None = None
    redirect_path: str | None = None

    def encode(self) -> str:
        return fernet.encrypt(self.model_dump_json().encode()).decode()

    @classmethod
    def decode(cls, encoded: str) -> OAuthRedirectState:
        decoded = fernet.decrypt(encoded).decode()
        return cls.model_validate_json(decoded)
