import datetime as dt
from collections.abc import Sequence
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
from convergence_games.db.enums import Role
from convergence_games.db.models import User, UserEventRole
from convergence_games.settings import SETTINGS


def build_token_extras(user: User, event_roles: Sequence[UserEventRole]) -> dict[str, Any]:
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "over_18": user.over_18,
        "event_roles": [{"role": r.role.value, "event_id": r.event_id} for r in event_roles],
    }


def _user_from_token_claims(user_id: int, extras: dict[str, Any]) -> User:
    user = User(id=user_id, first_name=extras["first_name"], last_name=extras["last_name"], over_18=extras["over_18"])
    user.event_roles = [
        UserEventRole(role=Role(r["role"]), event_id=r["event_id"], user_id=user_id)
        for r in extras.get("event_roles", [])
    ]
    return user


async def retrieve_user_handler(token: CustomToken, connection: ASGIConnection) -> User | None:
    user_id = int(token.sub)
    user_id_ctx.set(user_id)

    if "first_name" in token.extras:
        return _user_from_token_claims(user_id, token.extras)

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as async_session:
        async with async_session.begin():
            stmt = select(User).options(selectinload(User.event_roles)).where(User.id == user_id)
            user = (await async_session.execute(stmt)).scalar_one_or_none()
            async_session.expunge_all()

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
