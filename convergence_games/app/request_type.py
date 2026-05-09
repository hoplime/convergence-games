from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, override

from litestar.connection import ASGIConnection
from litestar.security.jwt import Token

# This file is responsible for exporting the following types:
# - CustomToken: The type of the token object for the JWT cookie authentication.
# - Request: The type of the request object for handlers and middleware.
# - TypedASGIConnection: The type of the connection object for handlers and middleware.

type TokenType = Literal["legacy", "access", "refresh"]


@dataclass
class CustomToken(Token):
    token_type: TokenType = "legacy"


type AnyASGIConnection = ASGIConnection[Any, Any, Any, Any]  # pyright: ignore[reportExplicitAny]

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar import Request as _Request
    from litestar.datastructures import Cookie, State
    from litestar.handlers.http_handlers import HTTPRouteHandler
    from litestar.plugins.htmx import HTMXDetails
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from convergence_games.db.models import User

    class AppState(State):
        db_engine: AsyncEngine
        session_maker_class: async_sessionmaker[AsyncSession]

    class RequestState(State):
        pending_auth_cookies: list[Cookie]
        current_session_jti: str | None

    class AppWithState(Litestar):
        state: AppState

    # This is a workaround for the HTMXRequest not being a generic type, and us wanting to annotate the User type.
    class HTMXRequest(_Request[User | None, CustomToken, RequestState]):
        htmx: HTMXDetails  # pyright: ignore[reportUninitializedInstanceVariable]

        @property
        @override
        def app(self) -> AppWithState: ...

    class TypedASGIConnection(ASGIConnection[HTTPRouteHandler, User | None, CustomToken, RequestState]):
        @property
        @override
        def app(self) -> AppWithState: ...

    Request: TypeAlias = HTMXRequest
else:
    from litestar.connection import ASGIConnection
    from litestar.plugins.htmx import HTMXRequest

    AppState = State
    RequestState = State
    AppWithState = Litestar
    TypedASGIConnection = ASGIConnection
    Request: TypeAlias = HTMXRequest
