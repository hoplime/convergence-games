from typing import cast

# from app.security.jwt import decode_jwt_token
from litestar.connection import ASGIConnection

# from litestar.exceptions import NotAuthorizedException
from litestar.middleware import (
    AbstractAuthenticationMiddleware,
    AuthenticationResult,
)
from litestar.middleware.base import DefineMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from convergence_games.app.constants import AUTH_COOKIE_NAME
from convergence_games.app.context import user_id_ctx
from convergence_games.db.models import User


class MockAuthenticationMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        auth_cookie = connection.cookies.get(AUTH_COOKIE_NAME)
        if not auth_cookie:
            return AuthenticationResult(user=None, auth={})

        user_id = int(auth_cookie)  # TODO: Replace with actual JWT decoding

        engine = cast(AsyncEngine, connection.app.state.db_engine)
        async with AsyncSession(engine) as async_session:
            async with async_session.begin():
                stmt = select(User).where(User.id == user_id)
                user = (await async_session.execute(stmt)).scalar_one_or_none()
                async_session.expunge_all()

        user_id_ctx.set(user_id)
        return AuthenticationResult(user=user, auth={"user_id": user_id})


mock_authentication_middleware = DefineMiddleware(MockAuthenticationMiddleware)
