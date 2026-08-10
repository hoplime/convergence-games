from datetime import datetime
from typing import Annotated

from litestar import Controller, Response, get, put
from litestar.di import Provide
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK, HTTP_204_NO_CONTENT
from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from convergence_games.db.models import Event, Game, GameRequirement, Room, Session, User
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from .._common import PutEventManageScheduleSession, user_can_manage_submissions
from ..services import ScheduleService, provide_schedule_service


class PutEventManageScheduleForm(BaseModel):
    sessions: list[PutEventManageScheduleSession]
    commit: bool = False


class ScheduleController(Controller):
    guards = [user_guard]
    dependencies = {
        "permission": permission_check(user_can_manage_submissions),
        "schedule_service": Provide(provide_schedule_service),
    }

    @get(
        path="/event/{event_sqid:str}/manage-schedule",
        dependencies={
            "event": event_with(
                selectinload(Event.games).options(
                    selectinload(Game.game_requirement).selectinload(GameRequirement.available_time_slots),
                    selectinload(Game.gamemaster),
                    selectinload(Game.sessions),
                ),
                selectinload(Event.rooms).selectinload(Room.tables),
                selectinload(Event.time_slots),
                selectinload(Event.tables),
                selectinload(Event.sessions).selectinload(Session.game),
            ),
        },
    )
    async def get_event_manage_schedule(
        self,
        request: Request,
        event: Event,
        permission: bool,
        schedule_service: ScheduleService,
    ) -> Template:
        return HTMXBlockTemplate(
            template_name="pages/event_manage_schedule.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "unscheduled_games": schedule_service.unscheduled_games(event),
                "sessions_by_table_and_time_slot": schedule_service.sessions_by_table_and_time_slot(event),
            },
        )

    @put(
        path="/event/{event_sqid:str}/manage-schedule",
        dependencies={
            "event": event_with(
                selectinload(Event.sessions),
            ),
        },
    )
    async def put_event_manage_schedule(
        self,
        event: Event,
        permission: bool,
        schedule_service: ScheduleService,
        data: Annotated[PutEventManageScheduleForm, Body(media_type=RequestEncodingType.JSON)],
    ) -> Response[str]:
        print(data)
        schedule_service.replace_sessions(event, data.sessions, commit=data.commit)

        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @get(
        path="/event/{event_sqid:str}/manage-schedule/last-updated-by",
        dependencies={
            "event": event_with(
                selectinload(Event.sessions).selectinload(Session.updated_by_user),
            ),
        },
    )
    async def get_event_manage_schedule_last_updated(
        self,
        event: Event,
        user: User,
        schedule_service: ScheduleService,
        last_saved: Annotated[datetime | None, Parameter(query="last-saved")] = None,
    ) -> Response[str]:
        return Response(
            content=schedule_service.last_updated_summary(event, user.id, last_saved),
            status_code=HTTP_200_OK,
        )
