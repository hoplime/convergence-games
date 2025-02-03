from litestar import Controller, get
from litestar.exceptions import NotFoundException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import Event
from convergence_games.db.ocean import sink


class GamesController(Controller):
    @get(path="/games")
    async def get_games(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/games.html.jinja", block_name=request.htmx.target)

    @get(path="/submit_game/{event_sqid:str}")
    async def submit_game(self, request: Request, db_session: AsyncSession, event_sqid: str) -> Template:
        event_id = sink(event_sqid)
        event = (
            await db_session.execute(select(Event).options(selectinload(Event.time_slots)).where(Event.id == event_id))
        ).scalar_one_or_none()

        if not event:
            raise NotFoundException()

        print(event.time_slots)

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
            },
        )
