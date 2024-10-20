from typing import TYPE_CHECKING, Any, TypeAlias

from litestar.datastructures import State

from convergence_games.db.models import User

if TYPE_CHECKING:
    from litestar import Request as _Request
    from litestar.contrib.htmx.request import HTMXDetails

    class HTMXRequest(_Request[User, dict[str, Any], State]):
        htmx: HTMXDetails

    Request: TypeAlias = HTMXRequest
else:
    from litestar.contrib.htmx.request import HTMXRequest

    Request: TypeAlias = HTMXRequest
