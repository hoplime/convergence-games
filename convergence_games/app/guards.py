from litestar.connection import ASGIConnection
from litestar.handlers.base import BaseRouteHandler

from convergence_games.app.exceptions import UserNotLoggedInError


async def user_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    # Check if the user is logged in
    if connection.user is None:
        raise UserNotLoggedInError("User must be logged in to perform this action.")
