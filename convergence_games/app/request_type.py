from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

from litestar.datastructures import Cookie, State
from litestar.security.jwt import Token

from convergence_games.db.models import User

# This file is responsible for exporting the following types:
# - CustomToken: The type of the token object for the JWT cookie authentication.
# - Request: The type of the request object for handlers and middleware.
# - ASGIConnection: The type of the connection object for handlers and middleware.
# - AppState: Typed application-level state (app.state), populated by the SQLAlchemy plugin.
# - RequestState: Typed per-request state (request.state / scope["state"]),
#     includes AppState attrs plus middleware-injected auth state.


type TokenType = Literal["access", "refresh", "legacy"]


@dataclass
class CustomToken(Token):
    token_type: TokenType = "legacy"

    def __post_init__(self) -> None:
        super().__post_init__()
        # Lift token_type out of `extras` if it was carried there (Litestar's Token.decode
        # stuffs all non-standard claims into `extras`).
        raw = self.extras.pop("token_type", None)
        if raw in ("access", "refresh", "legacy"):
            self.token_type = raw


if TYPE_CHECKING:
    from litestar import Litestar
    from litestar import Request as _Request
    from litestar.connection import ASGIConnection as _ASGIConnection
    from litestar.handlers.http_handlers import HTTPRouteHandler
    from litestar.plugins.htmx import HTMXDetails
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    class AppState(State):
        """Typed application-level state (app.state).

        Populated by the SQLAlchemy plugin (Advanced Alchemy's
        engine_app_state_key / session_maker_app_state_key defaults).
        """

        db_engine: AsyncEngine
        session_maker_class: async_sessionmaker[AsyncSession]

    class RequestState(AppState):
        """Typed per-request state (request.state / scope["state"]).

        Inherits app-level state attrs (db_engine, session_maker_class) because
        Litestar merges app state into the per-request scope. Adds auth-middleware
        fields set by JWTMultiCookieAuthenticationMiddleware.
        """

        pending_auth_cookies: list[Cookie]
        current_session_jti: str | None

    class AppWithState(Litestar):
        """Litestar app with typed state for IDE hinting."""

        state: AppState  # pyright: ignore[reportIncompatibleVariableOverride]

    # This is a workaround for the HTMXRequest not being a generic type, and us wanting to annotate the User type.
    class HTMXRequest(_Request[User | None, CustomToken, RequestState]):
        htmx: HTMXDetails

        @property
        def app(self) -> AppWithState: ...  # pyright: ignore[reportIncompatibleMethodOverride]

    class ASGIConnection(_ASGIConnection[HTTPRouteHandler, User | None, CustomToken, RequestState]):
        @property
        def app(self) -> AppWithState: ...  # pyright: ignore[reportIncompatibleMethodOverride]

    Request: TypeAlias = HTMXRequest
else:
    from litestar.connection import ASGIConnection as ASGIConnection
    from litestar.plugins.htmx import HTMXRequest

    AppState = State
    RequestState = State

    Request: TypeAlias = HTMXRequest
