from typing import Annotated, Literal

from litestar import Controller, Response, get, put
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import Game, User, UserGamePreference
from convergence_games.db.ocean import Sqid, sink
from convergence_games.services import ImageLoader


class RatingPutData(BaseModel):
    rating: UserGamePreferenceValue


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

        game_image_urls = [
            {
                "full": await image_loader.get_image_path(image.lookup_key),
                "thumbnail": await image_loader.get_image_path(image.lookup_key, size=300),
            }
            for image in game.images
        ]

        return HTMXBlockTemplate(
            template_name="pages/game.html.jinja",
            block_name=request.htmx.target,
            context={
                "game": game,
                "game_image_urls": game_image_urls,
            },
        )

    @put(path="/{game_sqid:str}/preference")
    async def put_game_preference(
        self,
        game_sqid: Sqid,
        user: User,
        transaction: AsyncSession,
        data: Annotated[RatingPutData, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        game_id: int = sink(game_sqid)
        user_game_preference = (
            await transaction.execute(
                select(UserGamePreference).where(
                    UserGamePreference.game_id == game_id,
                    UserGamePreference.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if user_game_preference is None:
            user_game_preference = UserGamePreference(game_id=game_id, user_id=user.id)
        user_game_preference.preference = data.rating
        transaction.add(user_game_preference)
        return Response(content="", status_code=204)
