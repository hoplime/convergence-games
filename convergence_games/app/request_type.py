from typing import TYPE_CHECKING, Any, TypeAlias

from litestar.datastructures import State

from convergence_games.db.models import User

if TYPE_CHECKING:
    from litestar import Request as _Request
    from litestar.plugins.htmx import HTMXDetails

    # This is a workaround for the HTMXRequest not being a generic type, and us wanting to annotate the User type.
    class HTMXRequest(_Request[User | None, dict[str, Any], State]):
        htmx: HTMXDetails

    Request: TypeAlias = HTMXRequest
else:
    from litestar.plugins.htmx import HTMXRequest

    Request: TypeAlias = HTMXRequest
