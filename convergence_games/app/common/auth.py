from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet
from litestar.exceptions import HTTPException
from litestar.response import Redirect
from pydantic import BaseModel
from sqlalchemy import String, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import User, UserLogin
from convergence_games.db.ocean import Sqid
from convergence_games.settings import SETTINGS


@dataclass
class ProfileInfo:
    user_first_name: str | None = None
    user_last_name: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    user_profile_picture: str | None = None


async def authorize_flow(
    transaction: AsyncSession,
    provider_name: LoginProvider,
    profile_info: ProfileInfo,
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
    # TODO: If linking_account_id is not None, but there is a UserLogin for this provider under a different provider user...
    # Maybe prevent that from happening in the first place by disallowing starting the linking process if there is already a login for this provider and this user?
    # Currently the front end doesn't allow this on a single tab but it's easy to mess up

    if user_login is None:
        # This account hasn't been used to login before
        # Create the new login
        user_login = UserLogin(
            provider=provider_name,
            provider_user_id=profile_info.user_id,
            provider_email=profile_info.user_email,
        )

        # Create the new user if there is no existing user
        # Otherwise, link the new login to the existing user
        if linking_account_id is None:
            user = User(
                first_name=profile_info.user_first_name or "",
                last_name=profile_info.user_last_name or "",
                logins=[user_login],
            )
            transaction.add(user)
        else:
            user = (await transaction.execute(select(User).where(User.id == linking_account_id))).scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            user.logins.append(user_login)
            transaction.add(user_login)
    else:
        # This account has been used to login before
        user_login_user = user_login.user

        if linking_account_id is None:
            # This is just a normal login
            user = user_login_user
        else:
            # This is a linking login
            if user_login_user.id != linking_account_id:
                # TODO: Possibly merge the two accounts instead of just rejecting the linking
                raise HTTPException(
                    status_code=403,
                    detail="Another account is already linked to this provider! Login to that account instead.",
                )
            user = user_login_user

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
