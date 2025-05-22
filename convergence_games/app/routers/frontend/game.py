from litestar import Controller, get
from litestar.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import Game
from convergence_games.db.ocean import Sqid, sink
from convergence_games.services import ImageLoader


class GameController(Controller):
    path = "/game"

    @get(path="/{game_sqid:str}")
    async def get_game(
        self,
        request: Request,
        game_sqid: Sqid,
        transaction: AsyncSession,
        image_loader: ImageLoader,
    ) -> Template:
        game_id: int = sink(game_sqid)
        game = (
            await transaction.execute(
                select(Game)
                .options(
                    selectinload(Game.system),
                    selectinload(Game.gamemaster),
                    selectinload(Game.event),
                    selectinload(Game.game_requirement),
                    selectinload(Game.genres),
                    selectinload(Game.content_warnings),
                    selectinload(Game.images),
                )
                .where(Game.id == game_id)
            )
        ).scalar_one_or_none()

        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        game_image_urls = [await image_loader.get_image_path(image.lookup_key) for image in game.images]

        return HTMXBlockTemplate(
            template_name="pages/game.html.jinja",
            block_name=request.htmx.target,
            context={"game": game, "game_image_urls": game_image_urls},
        )
