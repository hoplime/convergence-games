from litestar import Controller, get, post
from litestar.di import Provide
from litestar.response import Redirect
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import TimeSlotStatus
from convergence_games.db.models import TimeSlot, User
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.deps import time_slot_with
from convergence_games.lib.guards import user_guard
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template
from convergence_games.lib.template import catalog

from ..services import PartyService, provide_party_service


class PartyController(Controller):
    path = "/party"
    guards = [user_guard]
    dependencies = {"party_service": Provide(provide_party_service)}

    @get(
        path="/overview/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(raise_404=True),
        },
    )
    async def overview_party(
        self, time_slot: TimeSlot, user: User, request: Request, party_service: PartyService
    ) -> Template:
        overview = await party_service.get_overview(user=user, time_slot=time_slot)

        return HTMXBlockTemplate(
            template_str=catalog.render(
                "PartyOverview",
                time_slot=time_slot,
                party=overview.party,
                leader_id=overview.leader_id,
                request=request,
                max_party_size=overview.max_party_size,
                checked_in=overview.checked_in,
                is_gm=overview.is_gm,
                allocated_session=overview.allocated_session,
                allocated_session_players=overview.allocated_session_players,
            )
        )

    @post(
        path="/host/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def host_party(
        self,
        user: User,
        time_slot: TimeSlot | None,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        await party_service.host_party(user_id=user.id, time_slot_id=time_slot.id)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @get(path="/join")
    async def join_empty_party(self) -> Template:
        raise AlertError([Alert(alert_class="alert-error", message="No party found with that code.")])

    @get(
        path="/join/{time_slot_sqid:str}/{invite_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(selectinload(TimeSlot.event)),
        },
    )
    async def join_party(
        self,
        user: User,
        request: Request,
        time_slot: TimeSlot | None,
        invite_sqid: Sqid,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        party = await party_service.join_party(user_id=user.id, time_slot_id=time_slot.id, invite_sqid=invite_sqid)

        if not request.htmx:
            # This is from a QRCode - go to the overall planner view
            return Redirect(f"/event/{swim(party.time_slot.event)}/planner/{swim(time_slot)}")

        return Redirect(f"/party/overview/{swim(party.time_slot)}")

    @post(
        path="/leave/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def leave_party(
        self,
        user: User,
        time_slot: TimeSlot | None,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        await party_service.leave_party(user_id=user.id, time_slot_id=time_slot.id)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @get(
        path="/members/{time_slot_sqid:str}",
        dependencies={"time_slot": time_slot_with()},
    )
    async def get_party_members(
        self,
        user: User,
        time_slot: TimeSlot | None,
        party_service: PartyService,
    ) -> Template:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        party = await party_service.get_party_with_members(user_id=user.id, time_slot_id=time_slot.id)

        if party is None:
            raise AlertError([Alert(alert_class="alert-warning", message="No party found for this time slot.")])

        raise AlertError(
            [
                Alert(
                    alert_class="alert-info",
                    message=f"Party members for {time_slot.name}: {', '.join([member.full_name + (' (Leader)' if member.id in [u.user_id for u in party.party_user_links if u.is_leader] else '') for member in party.members])}",
                )
            ]
        )

    @post(
        path="/promote/{time_slot_sqid:str}/{member_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def promote_party_member(
        self,
        user: User,
        time_slot: TimeSlot | None,
        member_sqid: Sqid,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        await party_service.promote_member(user_id=user.id, time_slot_id=time_slot.id, member_sqid=member_sqid)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/remove/{time_slot_sqid:str}/{member_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def remove_party_member(
        self,
        user: User,
        time_slot: TimeSlot | None,
        member_sqid: Sqid,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        member_id = sink(member_sqid)

        await party_service.remove_member(user_id=user.id, time_slot_id=time_slot.id, member_id=member_id)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/checkin/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def check_in(
        self,
        user: User,
        time_slot: TimeSlot | None,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        await party_service.check_in(
            user_id=user.id, time_slot_id=time_slot.id, checkin_open_time=time_slot.checkin_open_time
        )

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/checkout/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def check_out(
        self,
        user: User,
        time_slot: TimeSlot | None,
        party_service: PartyService,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        await party_service.check_out(user_id=user.id, time_slot_id=time_slot.id)

        return Redirect(f"/party/overview/{swim(time_slot)}")
