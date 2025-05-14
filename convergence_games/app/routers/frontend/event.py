from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.guards import permission_check, user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import SubmissionStatus
from convergence_games.db.models import Event, Game, User
from convergence_games.db.ocean import Sqid, sink
from convergence_games.permissions import user_has_permission


async def get_event(event_sqid: Sqid, transaction: AsyncSession) -> Event:
    event_id: int = sink(event_sqid)
    event = (
        await transaction.execute(
            select(Event)
            .options(
                selectinload(Event.games).options(
                    selectinload(Game.system),
                    selectinload(Game.gamemaster),
                    selectinload(Game.game_requirement),
                    selectinload(Game.genres),
                ),
            )
            .where(Event.id == event_id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def can_approve(user: User, event: Event) -> bool:
    return user_has_permission(user, "game", (event, "all"), "approve")


class EventController(Controller):
    path = "/event"
    dependencies = {"event": Provide(get_event)}

    @get(path="/{event_sqid:str}", guards=[user_guard])
    async def get_event(
        self,
        request: Request,
        event: Event,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event.html.jinja",
            block_name=request.htmx.target,
            context={"event": event},
        )

    @get(
        path="/{event_sqid:str}/manage-submissions",
        guards=[user_guard],
        dependencies={"permission": permission_check(can_approve)},
    )
    async def get_event_manage_submissions(
        self,
        request: Request,
        event: Event,
        permission: bool,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_manage_submissions.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "submission_status": SubmissionStatus,
            },
        )
