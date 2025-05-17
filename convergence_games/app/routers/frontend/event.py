from collections.abc import Callable
from typing import Any, Literal, Sequence

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
    transaction: AsyncSession,
    event_sqid: Sqid | None = None,
) -> Event:
    event_id: int = sink(event_sqid) if event_sqid is not None else 1
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
    query_order_by: InstrumentedAttribute | None = {
        "title": Game.name,
        "submitted": Game.created_at,
        "status": Game.submission_status,
    }.get(sort)
    if query_order_by is not None and desc:
        query_order_by = query_order_by.desc()  # type: ignore

    stmt = (
        select(Game)
        .options(
            selectinload(Game.system),
            selectinload(Game.gamemaster),
            selectinload(Game.game_requirement),
            selectinload(Game.event),
        )
        .order_by(query_order_by)
        .where(Game.event_id == event_id)
    )
    games = (await transaction.execute(stmt)).scalars().all()

    if query_order_by is None:
        post_order_by: Callable[[Game], Any] = {
            "system": lambda g: g.system.name.lower(),
            "gamemaster": lambda g: g.gamemaster.last_name.lower(),
            "sessions": lambda g: g.game_requirement.times_to_run,
        }.get(sort)  # type: ignore

        games = sorted(games, key=post_order_by, reverse=desc)

    return games


async def get_event_approved_games_dep(
    event: Event,
    transaction: AsyncSession,
) -> Sequence[Game]:
    event_id: int = event.id
    stmt = (
        select(Game)
        .options(
            selectinload(Game.system),
            selectinload(Game.gamemaster),
            selectinload(Game.game_requirement),
            selectinload(Game.genres),
            selectinload(Game.content_warnings),
            selectinload(Game.event),
        )
        .order_by(Game.name)
        .where(
            Game.event_id == event_id,
            Game.submission_status == SubmissionStatus.APPROVED,
        )
    )
    games = (await transaction.execute(stmt)).scalars().all()
    return games


def user_can_manage_submissions(user: User, event: Event) -> bool:
    return user_has_permission(user, "event", (event, event), "manage_submissions")


class EventController(Controller):
    dependencies = {
        "event": Provide(get_event_dep),
    }

    # @get(
    #     path="/{event_sqid:str}",
    #     guards=[user_guard],
    # )
    # async def get_event(
    #     self,
    #     request: Request,
    #     event: Event,
    # ) -> Template:
    #     return HTMXBlockTemplate(
    #         template_name="pages/event.html.jinja",
    #         block_name=request.htmx.target,
    #         context={"event": event},
    #     )

    @get(
        ["/event/{event_sqid:str}", "/event/{event_sqid:str}/games", "/games"],
        dependencies={
            "games": Provide(get_event_approved_games_dep),
        },
    )
    async def get_event_games(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_games.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "games": games,
                "submission_status": SubmissionStatus,
            },
        )

    @get(
        path="/event/{event_sqid:str}/manage-submissions",
        guards=[user_guard],
        dependencies={
            "permission": permission_check(user_can_manage_submissions),
            "games": Provide(get_event_games_dep),
        },
    )
    async def get_event_manage_submissions(
        self,
        request: Request,
        event: Event,
        games: Sequence[Game],
        permission: bool,
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
