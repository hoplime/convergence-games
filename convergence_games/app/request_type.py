from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from litestar.datastructures import State
from litestar.security.jwt import Token

from convergence_games.db.models import User

# This file is responsible for exporting the following types:
# - Token: The type of the token object for the JWT cookie authentication.
# - Request: The type of the request object for handlers and middleware.
# - ASGIConnection: The type of the connection object for handlers and middleware.


@dataclass
class CustomToken(Token):
    flag: bool = False


if TYPE_CHECKING:
    from litestar import Request as _Request
    from litestar.connection import ASGIConnection as _ASGIConnection
    from litestar.handlers.http_handlers import HTTPRouteHandler
    from litestar.plugins.htmx import HTMXDetails

    # This is a workaround for the HTMXRequest not being a generic type, and us wanting to annotate the User type.
    class HTMXRequest(_Request[User | None, CustomToken, State]):
        htmx: HTMXDetails

    class ASGIConnection(_ASGIConnection[HTTPRouteHandler, User | None, CustomToken, State]):
        pass

    Request: TypeAlias = HTMXRequest
else:
    from litestar.connection import ASGIConnection as ASGIConnection
    from litestar.plugins.htmx import HTMXRequest

    Request: TypeAlias = HTMXRequest
