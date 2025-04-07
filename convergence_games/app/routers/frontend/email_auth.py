from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Annotated

from litestar import Controller, get, post
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Redirect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
from convergence_games.db.models import User, UserEmailVerificationCode, UserLogin


async def login_with_email_and_code(
    email: str,
    code: str,
    transaction: AsyncSession,
) -> Redirect:
    stmt = (
        select(UserEmailVerificationCode)
        .where(UserEmailVerificationCode.code == code)
        .where(UserEmailVerificationCode.email == email)
    )
    user_email_verification_code = (x := await transaction.execute(stmt)).scalar_one_or_none()

    if user_email_verification_code is None:
        raise HTTPException(status_code=401, detail="Invalid code or code expired")

    user_login = (
        await transaction.execute(
            select(UserLogin).where(
                UserLogin.provider == "email",
                UserLogin.provider_user_id == email,
            )
        )
    ).scalar_one_or_none()

    if user_login is None:
        # We need to create a new user and login
        user = User(
            name="",
            logins=[
                UserLogin(
                    provider="email",
                    provider_user_id=email,
                    provider_email=email,
                )
            ],
        )
        transaction.add(user)
        await transaction.flush()
        user_id = user.id
    else:
        user_id = user_login.user_id

    login = jwt_cookie_auth.login(str(user_id))

    return Redirect(path="/profile", cookies=login.cookies)


@dataclass
class PostVerifyCodeForm:
    email: str
    code: str


class EmailAuthController(Controller):
    path = "/email_auth"

    @get(path="/magic_link")
    async def get_magic_link(
        self, magic_link_code: Annotated[str, Parameter(query="code")], transaction: AsyncSession
    ) -> Redirect:
        code, email = UserEmailVerificationCode.decode_magic_link_code(magic_link_code)
        return await login_with_email_and_code(email, code, transaction)

    @post(path="/verify_code")
    async def post_verify_code(
        self,
        data: Annotated[PostVerifyCodeForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
    ) -> Redirect:
        return await login_with_email_and_code(data.email, data.code, transaction)
