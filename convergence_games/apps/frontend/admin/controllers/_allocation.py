from typing import Annotated, Literal

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Redirect, Response, Template
from litestar.status_codes import HTTP_204_NO_CONTENT
from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import TimeSlotStatus
from convergence_games.db.models import Event
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from .._common import PutEventManageAllocationSession, user_can_manage_submissions
from ..services import AllocationService, provide_allocation_service


class PutEventManageAllocationForm(BaseModel):
    allocations: list[PutEventManageAllocationSession]
    commit: bool = False


class AllocationController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(selectinload(Event.time_slots)),
        "permission": permission_check(user_can_manage_submissions),
        "allocation_service": Provide(provide_allocation_service),
    }

    @get(
        path=[
            "/event/{event_sqid:str}/manage-allocation",
            "/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}",
        ],
    )
    async def get_event_manage_allocation(
        self,
        request: Request,
        event: Event,
        permission: bool,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid | None, Parameter()] = None,
    ) -> Template:
        time_slot = allocation_service.resolve_time_slot(event, time_slot_sqid)
        sessions = await allocation_service.committed_sessions_for_slot(time_slot.id)
        groups = await allocation_service.allocation_groups(time_slot, sessions)
        any_existing_compensation = await allocation_service.compensation_applied(event.id, time_slot.id)

        return HTMXBlockTemplate(
            template_name="pages/event_manage_allocation.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "selected_time_slot": time_slot,
                "compensated": "Compensated" if any_existing_compensation else "Uncompensated",
                "sessions": sessions,
                "groups": groups,
            },
        )

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/do-allocation",
    )
    async def post_event_do_allocation(
        self,
        event: Event,
        permission: bool,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> Redirect:
        time_slot_id = sink(time_slot_sqid)

        await allocation_service.freeze_user_game_preferences(time_slot_id)
        await allocation_service.run_allocation(time_slot_id)

        return Redirect(f"/event/{swim(event)}/manage-allocation/{time_slot_sqid}")

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/unlock",
    )
    async def post_event_unlock_allocation(
        self,
        permission: bool,
        event: Event,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        return allocation_service.set_time_slot_status(event, time_slot_sqid, TimeSlotStatus.PRE_ALLOCATION).value

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/lock",
    )
    async def post_event_lock_allocation(
        self,
        permission: bool,
        event: Event,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        return allocation_service.set_time_slot_status(event, time_slot_sqid, TimeSlotStatus.ALLOCATING).value

    @post(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/{user_sqid:str}/checkin",
    )
    async def post_event_checkin_player(
        self,
        permission: bool,
        event: Event,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
        user_sqid: Annotated[Sqid, Parameter()],
        data: Annotated[dict[Literal["checkin"], Literal["on"]], Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)
        user_id = sink(user_sqid)
        should_checkin = data.get("checkin", "off") == "on"

        await allocation_service.set_checkin(time_slot_id=time_slot_id, user_id=user_id, checked_in=should_checkin)

        return "checked-in"

    @put(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}",
    )
    async def put_event_manage_allocation(
        self,
        permission: bool,
        event: Event,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
        data: Annotated[PutEventManageAllocationForm, Body(media_type=RequestEncodingType.JSON)],
    ) -> Response[str]:
        time_slot = next(
            (ts for ts in event.time_slots if ts.id == sink(time_slot_sqid)),
            None,
        )

        if time_slot is None:
            raise HTTPException(status_code=404, detail="Time slot not found")

        await allocation_service.replace_allocations(time_slot, data.allocations, commit=data.commit)

        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @put(
        path="/event/{event_sqid:str}/manage-allocation/{time_slot_sqid:str}/apply-compensation",
    )
    async def put_event_apply_compensation(
        self,
        permission: bool,
        event: Event,
        allocation_service: AllocationService,
        time_slot_sqid: Annotated[Sqid, Parameter()],
    ) -> str:
        time_slot_id = sink(time_slot_sqid)
        # Read the event ID up front: apply_compensation calls expunge_all(), which detaches
        # every instance in the identity map (including `event`) from the session.
        event_id = event.id

        await allocation_service.apply_compensation(event_id, time_slot_id)

        return "Compensated"
