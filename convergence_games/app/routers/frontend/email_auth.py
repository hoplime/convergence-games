from __future__ import annotations

from typing import Annotated

from litestar import Controller, get, post
from litestar.params import Parameter
from litestar.response import Redirect
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
from convergence_games.db.models import UserEmailVerificationCode


async def login_with_email_and_code(
    email: str,
    code: str,
    transaction: AsyncSession,
) -> Redirect:
    user_id = 1  # TODO: Get user ID from magic link code
    login = jwt_cookie_auth.login(str(user_id))

    return Redirect(path="/profile", cookies=login.cookies)


class EmailAuthController(Controller):
    path = "/email_auth"

    @get(path="/magic_link")
    async def get_magic_link(
        self, magic_link_code: Annotated[str, Parameter(query="code")], transaction: AsyncSession
    ) -> Redirect:
        code, email = UserEmailVerificationCode.decode_magic_link_code(magic_link_code)
        return await login_with_email_and_code(code, email, transaction)

    @post(path="/verify_code")
    async def post_verify_code(self, email: str, code: str, transaction: AsyncSession) -> Redirect:
        return await login_with_email_and_code(code, email, transaction)
