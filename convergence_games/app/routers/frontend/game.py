from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.datastructures import Cookie
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCoreActivity,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
    SubmissionStatus,
)
from convergence_games.db.models import Event, Game
from convergence_games.db.ocean import Sqid, sink


class GameController(Controller):
    @get(path="/game/{game_sqid:str}")
    async def get_game(
        self,
        request: Request,
        game_sqid: Sqid,
        transaction: AsyncSession,
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
                )
                .where(Game.id == game_id)
            )
        ).scalar_one_or_none()

        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        return HTMXBlockTemplate(
            template_name="pages/game.html.jinja",
            block_name=request.htmx.target,
            context={"game": game},
        )

    @get(path="/game/{game_sqid:str}/edit")
    async def get_game_edit(
        self,
        request: Request,
        game_sqid: Sqid,
        transaction: AsyncSession,
    ) -> HTMXBlockTemplate:
        game_id: int = sink(game_sqid)
        game = (
            await transaction.execute(
                select(Game)
                .options(
                    selectinload(Game.system),
                    selectinload(Game.gamemaster),
                    selectinload(Game.event, Event.time_slots),
                    selectinload(Game.game_requirement),
                    selectinload(Game.genres),
                    selectinload(Game.content_warnings),
                )
                .where(Game.id == game_id)
            )
        ).scalar_one_or_none()

        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "game": game,
                "event": game.event,
                "tones": GameTone,
                "crunches": GameCrunch,
                "core_activities": GameCoreActivity,
                "ksps": GameKSP,
                "table_size_requirements": GameTableSizeRequirement,
                "equipment_requirements": GameEquipmentRequirement,
                "activity_requirements": GameActivityRequirement,
                "room_requirements": GameRoomRequirement,
            },
        )
