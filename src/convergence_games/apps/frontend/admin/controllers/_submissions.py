from collections.abc import Sequence
from typing import Literal

from litestar import Controller, get
from litestar.di import Provide
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import SubmissionStatus
from convergence_games.db.models import Event, Game
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from .._common import user_can_manage_submissions


# region Dependencies
async def get_event_games_dep(
    event: Event,  # This forces the dependencies to be in a chain, meaning the transaction isn't closed yet
    transaction: AsyncSession,
    sort: Literal["title", "system", "gamemaster", "submitted", "status", "sessions"] = "submitted",
    desc: bool = False,
) -> Sequence[Game]:
    event_id: int = event.id

    # TODO: Technical typing TODO - an eliminator or TypeIs check for the sort
    query_order_by = {
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

        def by_system(g: Game) -> str:
            return g.system.name.lower()

        def by_gamemaster(g: Game) -> str:
            return g.gamemaster.last_name.lower()

        def by_sessions(g: Game) -> int:
            return g.game_requirement.times_to_run

        post_order_by = {
            "system": by_system,
            "gamemaster": by_gamemaster,
            "sessions": by_sessions,
        }.get(sort)

        assert post_order_by is not None, "Invalid sort option"

        games = sorted(games, key=post_order_by, reverse=desc)

    return games


# endregion


class SubmissionsController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(),
        "permission": permission_check(user_can_manage_submissions),
    }

    @get(
        path="/event/{event_sqid:str}/manage-submissions",
        dependencies={
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
                "total_games": len(games),
                "total_systems": len({game.system.id for game in games}),
                "total_gamemasters": len({game.gamemaster.id for game in games}),
                "total_sessions": sum([game.game_requirement.times_to_run for game in games]),
                "total_approved_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.APPROVED
                    ]
                ),
                "total_draft_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.DRAFT
                    ]
                ),
                "total_submitted_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.SUBMITTED
                    ]
                ),
                "total_rejected_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.REJECTED
                    ]
                ),
                "total_cancelled_sessions": sum(
                    [
                        game.game_requirement.times_to_run
                        for game in games
                        if game.submission_status == SubmissionStatus.CANCELLED
                    ]
                ),
            },
        )
