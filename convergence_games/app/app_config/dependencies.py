from collections.abc import AsyncGenerator

from litestar.di import Provide
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_409_CONFLICT
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.exceptions import UserNotLoggedInError
from convergence_games.app.request_type import Request
from convergence_games.db.models import User
from convergence_games.services import ImageLoader, image_loader_from_settings


async def provide_transaction(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    try:
        async with db_session.begin():
            yield db_session
    except IntegrityError as exc:
        raise ClientException(
            status_code=HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


async def provide_user(
    request: Request,
) -> User:
    if request.user is None:
        raise UserNotLoggedInError("User must be logged in to perform this action.")
    return request.user


async def provide_image_loader() -> ImageLoader:
    return image_loader_from_settings


dependencies = {
    "transaction": Provide(provide_transaction),
    "user": Provide(provide_user),
    "image_loader": Provide(provide_image_loader),
}
