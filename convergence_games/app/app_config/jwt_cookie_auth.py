from typing import cast

from litestar.connection import ASGIConnection
from litestar.security.jwt import JWTCookieAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from convergence_games.app.context import user_id_ctx
from convergence_games.app.request_type import CustomToken
from convergence_games.db.models import User
from convergence_games.settings import SETTINGS


async def retrieve_user_handler(token: CustomToken, connection: ASGIConnection) -> User | None:
    print(f"Token: {token}")

    user_id = int(token.sub)

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as async_session:
        async with async_session.begin():
            stmt = select(User).where(User.id == user_id)
            user = (await async_session.execute(stmt)).scalar_one_or_none()
            async_session.expunge_all()

    print(f"User: {user}")

    user_id_ctx.set(user_id)
    return user


jwt_cookie_auth = JWTCookieAuth(
    retrieve_user_handler=retrieve_user_handler,
    token_secret=SETTINGS.TOKEN_SECRET,
    token_cls=CustomToken,
    exclude=["/oauth2"],
)
