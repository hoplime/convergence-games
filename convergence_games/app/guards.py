from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from litestar.connection import ASGIConnection
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.handlers.base import BaseRouteHandler

from convergence_games.app.exceptions import UserNotLoggedInError


async def user_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    # Check if the user is logged in
    if connection.user is None:
        raise UserNotLoggedInError("User must be logged in to perform this action.")


def permission_check(
    permission_check: Callable[..., bool],
    raise_on_failure: bool = True,
) -> Callable[..., Awaitable[bool]]:
    @wraps(permission_check)
    async def permission_success(*args: Any, **kwargs: Any) -> bool:
        result = permission_check(*args, **kwargs)
        if result:
            return True
        if raise_on_failure:
            raise HTTPException(
                status_code=403, detail="User does not have the required permission to perform this action."
            )
        return False

    return Provide(permission_success)
