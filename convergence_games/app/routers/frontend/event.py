from typing import Literal, Sequence

from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from convergence_games.app.guards import permission_check, user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import SubmissionStatus
from convergence_games.db.models import Event, Game, User
from convergence_games.db.ocean import Sqid, sink
from convergence_games.permissions import user_has_permission


async def get_event_dep(
    event_sqid: Sqid,
    transaction: AsyncSession,
) -> Event:
    event_id: int = sink(event_sqid)
    stmt = select(Event).where(Event.id == event_id)
    event = (await transaction.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


async def get_event_games_dep(
    event: Event,  # This forces the dependencies to be in a chain, meaning the transaction isn't closed yet
    transaction: AsyncSession,
    sort: Literal["title", "system", "gamemaster", "submitted", "status", "sessions"] = "submitted",
    desc: bool = False,
) -> Sequence[Game]:
    event_id: int = event.id
    order_by: InstrumentedAttribute = {
        "title": Game.name,
        "system": Game.system,
        "gamemaster": Game.gamemaster,
        "submitted": Game.created_at,
        "status": Game.submission_status,
        "sessions": Game.game_requirement,
    }[sort]
    if desc:
        order_by = order_by.desc()  # type: ignore

    stmt = (
        select(Game)
        .options(
            selectinload(Game.system),
            selectinload(Game.gamemaster),
            selectinload(Game.game_requirement),
            selectinload(Game.genres),
            selectinload(Game.event),
        )
        .order_by(order_by)
        .where(Game.event_id == event_id)
    )
    games = (await transaction.execute(stmt)).scalars().all()
    return games


def user_can_approve_all_games(user: User, event: Event) -> bool:
    return user_has_permission(user, "game", (event, "all"), "approve")


class EventController(Controller):
    path = "/event"
    dependencies = {
        "event": Provide(get_event_dep),
    }

    @get(
        path="/{event_sqid:str}",
        guards=[user_guard],
    )
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
        dependencies={
            "permission": permission_check(user_can_approve_all_games),
            "games": Provide(get_event_games_dep),
        },
    )
    async def get_event_manage_submissions(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        sort: Literal["title", "system", "gamemaster", "submitted", "status", "sessions"] = "submitted",
        desc: bool = False,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_manage_submissions.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "sort": sort,
                "desc": desc,
                "submission_status": SubmissionStatus,
            },
        )
