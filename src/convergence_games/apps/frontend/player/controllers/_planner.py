from __future__ import annotations

from typing import Annotated

from litestar import Controller, get
from litestar.di import Provide
from litestar.params import Parameter
from litestar.response import Template
from sqlalchemy.orm import selectinload

from convergence_games.db.models import Event, User
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import user_guard
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.permissions import user_has_permission
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from ..services import PlannerService, provide_planner_service


class PlannerController(Controller):
    dependencies = {"planner_service": Provide(provide_planner_service)}

    @get(
        ["/event/{event_sqid:str}/planner", "/event/{event_sqid:str}/planner/{time_slot_sqid:str}"],
        dependencies={"event": event_with(selectinload(Event.time_slots))},
        guards=[user_guard],
    )
    async def get_event_session_planner(
        self,
        request: Request,
        event: Event,
        user: User,
        planner_service: PlannerService,
        time_slot_sqid: Annotated[Sqid | None, Parameter()] = None,
    ) -> Template:
        if not event.is_planner_open() and not user_has_permission(
            user, "event", (event, event), "manage_submissions"
        ):
            return HTMXBlockTemplate(
                template_name="pages/event_planner_closed.html.jinja",
                block_name=request.htmx.target,
                context={"event": event},
            )

        time_slot_id = sink(time_slot_sqid) if time_slot_sqid is not None else None
        planner_data = await planner_service.get_planner_data(event=event, user=user, time_slot_id=time_slot_id)

        return HTMXBlockTemplate(
            template_name="pages/event_session_planner.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "selected_time_slot": planner_data.selected_time_slot,
                "game_tier_list": planner_data.game_tier_list,
                "preferences": planner_data.preferences,
                "user_game_playeds": planner_data.user_game_playeds,
                "party_leader": planner_data.party_leader,
                "all_party_members_over_18": planner_data.all_party_members_over_18,
                "scheduled_time_slots": planner_data.scheduled_time_slots,
                "has_d20": planner_data.has_d20,
                "all_party_members_have_d20": planner_data.all_party_members_have_d20,
                "any_party_member_has_played_and_wont_repeat": planner_data.any_party_member_has_played_and_wont_repeat,
                "downgraded_d20": planner_data.downgraded_d20,
            },
        )
