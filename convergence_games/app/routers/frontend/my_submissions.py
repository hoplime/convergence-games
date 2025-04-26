from litestar import Controller, Response, get
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.guards import user_guard
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
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    GameRequirement,
    GameRequirementTimeSlotLink,
    Genre,
    System,
)
from convergence_games.db.ocean import Sqid, sink


class MySubmissionsController(Controller):
    @get(path="/my-submissions", guards=[user_guard])
    async def get_my_submissions(
        self,
        request: Request,
        transaction: AsyncSession,
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        games_for_user_and_event = (
            (
                await transaction.execute(
                    select(Game)
                    .where(Game.gamemaster_id == request.user.id)
                    .options(selectinload(Game.game_requirement))
                )
            )
            .scalars()
            .all()
        )

        return HTMXBlockTemplate(
            template_name="pages/my_submissions.html.jinja",
            block_name=request.htmx.target,
            context={"games": games_for_user_and_event},
        )
