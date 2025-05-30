import datetime as dt
from typing import Any, cast

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.middleware.authentication import AuthenticationResult
from litestar.security.jwt import JWTCookieAuth, JWTCookieAuthenticationMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.context import user_id_ctx
from convergence_games.app.request_type import CustomToken
from convergence_games.db.models import User
from convergence_games.settings import SETTINGS


async def retrieve_user_handler(token: CustomToken, connection: ASGIConnection) -> User | None:
    user_id = int(token.sub)

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as async_session:
        async with async_session.begin():
            stmt = select(User).options(selectinload(User.event_roles)).where(User.id == user_id)
            user = (await async_session.execute(stmt)).scalar_one_or_none()
            async_session.expunge_all()

    user_id_ctx.set(user_id)
    return user


class LaxJWTCookieAuthenticationMiddleware(JWTCookieAuthenticationMiddleware):
    async def authenticate_request(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthenticationResult:
        try:
            return await super().authenticate_request(connection)
        except NotAuthorizedException:
            return AuthenticationResult(user=None, auth=None)


jwt_cookie_auth = JWTCookieAuth(
    token_secret=SETTINGS.TOKEN_SECRET,
    retrieve_user_handler=retrieve_user_handler,
    token_cls=CustomToken,
    authentication_middleware_class=LaxJWTCookieAuthenticationMiddleware,
    exclude=["/site.webmanifest", "/static"],
    default_token_expiration=dt.timedelta(days=365),  # 1 year
)
