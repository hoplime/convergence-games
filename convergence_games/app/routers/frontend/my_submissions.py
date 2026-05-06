from itertools import groupby

from litestar import Controller, get
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate
from convergence_games.db.models import Event, Game
from convergence_games.settings import SETTINGS


class MySubmissionsController(Controller):
    @get(path="/my-submissions", guards=[user_guard])
    async def get_my_submissions(
        self,
        request: Request,
        transaction: AsyncSession,
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        games = (
            (
                await transaction.execute(
                    select(Game)
                    .join(Event, Game.event_id == Event.id)
                    .where(Game.gamemaster_id == request.user.id)
                    .options(selectinload(Game.game_requirement), selectinload(Game.event))
                    .order_by(Event.start_date.desc(), Game.name)
                )
            )
            .scalars()
            .all()
        )

        # groupby works here because the query is sorted by event start_date desc
        games_by_event: list[tuple[Event, list[Game]]] = [
            (event, list(event_games)) for event, event_games in groupby(games, key=lambda g: g.event)
        ]

        default_event = (
            await transaction.execute(select(Event).where(Event.id == SETTINGS.DEFAULT_EVENT_ID))
        ).scalar_one_or_none()

        return HTMXBlockTemplate(
            template_name="pages/my_submissions.html.jinja",
            block_name=request.htmx.target,
            context={"games_by_event": games_by_event, "default_event": default_event},
        )
