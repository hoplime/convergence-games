from litestar import Controller, get
from sqlalchemy.orm import selectinload

from convergence_games.db.models import Event
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template

from .._common import user_can_manage_submissions


class AdminController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(selectinload(Event.time_slots)),
        "permission": permission_check(user_can_manage_submissions),
    }

    @get(path="/admin")
    async def get_admin(self, request: Request, event: Event, permission: bool) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/admin.html.jinja", block_name=request.htmx.target, context={"event": event}
        )
