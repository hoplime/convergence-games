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

from convergence_games.app.services.common_auth import ProfileInfo, authorize_flow
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import UserEmailVerificationCode
from convergence_games.db.ocean import Sqid, sink


async def login_with_email_and_code(
    email: str,
    code: str,
    transaction: AsyncSession,
    linking_account_id: int | None = None,
) -> Redirect:
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

    return await authorize_flow(
        transaction=transaction,
        provider_name=LoginProvider.EMAIL,
        profile_info=ProfileInfo(
            user_id=email,
            user_email=email,
        ),
        linking_account_id=linking_account_id,
    )


@dataclass
class PostVerifyCodeForm:
    email: str
    code: str


class EmailAuthController(Controller):
    path = "/email_auth"

    @get(path="/magic_link")
    async def get_magic_link(
        self,
        magic_link_code: Annotated[str, Parameter(query="code")],
        transaction: AsyncSession,
        linking_account_sqid: Sqid | None = None,
    ) -> Redirect:
        code, email = UserEmailVerificationCode.decode_magic_link_code(magic_link_code)
        return await login_with_email_and_code(
            email,
            code,
            transaction,
            linking_account_id=sink(linking_account_sqid) if linking_account_sqid is not None else None,
        )

    @post(path="/verify_code")
    async def post_verify_code(
        self,
        data: Annotated[PostVerifyCodeForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        transaction: AsyncSession,
        linking_account_sqid: Sqid | None = None,
    ) -> Redirect:
        return await login_with_email_and_code(
            data.email,
            data.code,
            transaction,
            linking_account_id=sink(linking_account_sqid) if linking_account_sqid is not None else None,
        )
