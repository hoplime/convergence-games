from typing import TYPE_CHECKING, Protocol

from fastapi import Request as FastAPIRequest
from starlette.datastructures import State as StarletteState

from convergence_games.db.session import StartupDBInfo

if TYPE_CHECKING:

    class _StateProto(Protocol):
        db: StartupDBInfo

    class CustomState(StarletteState, _StateProto): ...

    class Request(FastAPIRequest):
        state: CustomState
else:
    Request = FastAPIRequest
