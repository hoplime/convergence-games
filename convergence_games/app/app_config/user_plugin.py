from litestar import Request
from litestar.config.app import AppConfig
from litestar.di import Provide
from litestar.plugins import InitPluginProtocol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.context import user_id_ctx
from convergence_games.db.models import User


async def provide_user_id(db_session: AsyncSession, request: Request) -> int | None:
    # db_session is only dependended so that its Context is the same as the one where the user_id_ctx is set
    # TODO: This should all likely be middleware instead but it works for debugging for now
    user_id = 1
    user_id_ctx.set(user_id)
    return user_id


async def provide_user(user_id: int | None, db_session: AsyncSession) -> User | None:
    if user_id is None:
        return None

    stmt = select(User).where(User.id == user_id)
    async with db_session.begin():
        user = (await db_session.execute(stmt)).scalar_one_or_none()
        db_session.expunge_all()
    return user


class UserPlugin(InitPluginProtocol):
    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.dependencies["user_id"] = Provide(provide_user_id)
        app_config.dependencies["user"] = Provide(provide_user)
        return app_config


user_plugin = UserPlugin()
