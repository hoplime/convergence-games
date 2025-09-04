from __future__ import annotations

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.response import Redirect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.alerts import Alert, AlertError
from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import TimeSlotStatus
from convergence_games.db.models import (
    Event,
    Game,
    Party,
    PartyUserLink,
    Session,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventD20Transaction,
)
from convergence_games.db.ocean import Sqid, sink, sink_upper, swim


def party_with(*options: ExecutableOption, raise_404: bool = False) -> Provide:
    async def wrapper(
        transaction: AsyncSession,
        invite_sqid: Sqid,
    ) -> Party | None:
        try:
            party_id = sink_upper(invite_sqid)
            party = (
                await transaction.execute(select(Party).options(*options).where(Party.id == party_id))
            ).scalar_one_or_none()
        except Exception:
            party = None

        if not party and raise_404:
            raise HTTPException(status_code=404, detail="Party not found.")

        return party

    return Provide(wrapper)


def time_slot_with(*options: ExecutableOption, raise_404: bool = False) -> Provide:
    async def wrapper(
        transaction: AsyncSession,
        time_slot_sqid: Sqid,
    ) -> TimeSlot | None:
        time_slot_id: int = sink(time_slot_sqid)
        time_slot = (
            await transaction.execute(select(TimeSlot).options(*options).where(TimeSlot.id == time_slot_id))
        ).scalar_one_or_none()

        if not time_slot and raise_404:
            raise HTTPException(status_code=404, detail="Time slot not found.")

        return time_slot

    return Provide(wrapper)


async def user_is_gm_for_this_time_slot(
    transaction: AsyncSession,
    user: User,
    time_slot: TimeSlot,
) -> bool:
    return (
        await transaction.execute(
            select(Session.id)
            .join(Game, Session.game_id == Game.id)
            .where(Session.time_slot_id == time_slot.id, Game.gamemaster_id == user.id, Session.committed)
            .limit(1)
        )
    ).scalar_one_or_none() is not None


class PartyController(Controller):
    path = "/party"
    guards = [user_guard]

    @get(
        path="/overview/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(raise_404=True),
        },
    )
    async def overview_party(
        self, transaction: AsyncSession, time_slot: TimeSlot, user: User, request: Request
    ) -> Template:
        party = (
            await transaction.execute(
                select(Party)
                .where(Party.time_slot_id == time_slot.id)
                .where(Party.members.any(id=user.id))
                .options(
                    selectinload(Party.time_slot),
                    selectinload(Party.party_user_links),
                    selectinload(Party.members).options(
                        selectinload(User.checkin_statuses), selectinload(User.latest_d20_transaction)
                    ),
                    with_loader_criteria(UserCheckinStatus, UserCheckinStatus.time_slot_id == time_slot.id),
                    with_loader_criteria(
                        UserEventD20Transaction, UserEventD20Transaction.event_id == time_slot.event_id
                    ),
                )
            )
        ).scalar_one_or_none()
        checked_in = (
            await transaction.execute(
                select(UserCheckinStatus.checked_in)
                .where(UserCheckinStatus.user_id == user.id)
                .where(UserCheckinStatus.time_slot_id == time_slot.id)
            )
        ).scalar_one_or_none() or False
        is_gm = await user_is_gm_for_this_time_slot(transaction, user, time_slot)
        if party is None:
            leader_id = None
        else:
            leader_id = next((link.user_id for link in party.party_user_links if link.is_leader), None)
        max_party_size = (
            await transaction.execute(select(Event.max_party_size).where(Event.id == time_slot.event_id))
        ).scalar_one_or_none()
        return HTMXBlockTemplate(
            template_str=catalog.render(
                "PartyOverview",
                time_slot=time_slot,
                party=party,
                leader_id=leader_id,
                request=request,
                max_party_size=max_party_size,
                checked_in=checked_in,
                is_gm=is_gm,
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
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        is_gm = await user_is_gm_for_this_time_slot(transaction, user, time_slot)

        if is_gm:
            raise AlertError([Alert(alert_class="alert-error", message="GMs cannot host parties for their sessions.")])

        existing_party_for_time_slot = (
            await transaction.execute(
                select(Party).where(Party.time_slot_id == time_slot.id).where(Party.members.any(id=user.id))
            )
        ).scalar_one_or_none()

        if existing_party_for_time_slot:
            raise AlertError(
                [Alert(alert_class="alert-warning", message="You are already in a party for this time slot.")]
            )

        party = Party(
            time_slot_id=time_slot.id,
            created_by=user.id,
            updated_by=user.id,
            party_user_links=[PartyUserLink(user_id=user.id, is_leader=True)],
        )
        transaction.add(party)
        await transaction.flush()

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
        transaction: AsyncSession,
        user: User,
        request: Request,
        time_slot: TimeSlot | None,
        invite_sqid: Sqid,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        is_gm = await user_is_gm_for_this_time_slot(transaction, user, time_slot)

        if is_gm:
            raise AlertError([Alert(alert_class="alert-error", message="GMs cannot join parties for their sessions.")])

        existing_party_user_link = (
            await transaction.execute(
                select(PartyUserLink).where(
                    PartyUserLink.user_id == user.id, PartyUserLink.party.has(time_slot_id=time_slot.id)
                )
            )
        ).scalar_one_or_none()

        if existing_party_user_link is not None:
            time_slot = (
                await transaction.execute(select(TimeSlot).where(TimeSlot.id == time_slot.id))
            ).scalar_one_or_none()
            raise AlertError(
                [Alert(alert_class="alert-warning", message="You are already in a party for this time slot.")],
                redirect_url=f"/event/{swim('Event', time_slot.event_id)}/planner/{swim(time_slot)}"
                if time_slot
                else None,
                redirect_text="Return to Planner",
            )

        try:
            invite_id = sink_upper(invite_sqid)
        except Exception as e:
            raise AlertError([Alert(alert_class="alert-error", message="Invalid invite code.")]) from e

        party = (
            await transaction.execute(
                select(Party)
                .where(Party.id == invite_id, Party.time_slot_id == time_slot.id)
                .options(selectinload(Party.members), selectinload(Party.time_slot).selectinload(TimeSlot.event))
            )
        ).scalar_one_or_none()

        # TODO: Tidy these up
        if party is None:
            time_slot = (
                await transaction.execute(select(TimeSlot).where(TimeSlot.id == time_slot.id))
            ).scalar_one_or_none()
            raise AlertError(
                [Alert(alert_class="alert-error", message="No party found with that code.")],
                redirect_url=f"/event/{swim('Event', time_slot.event_id)}/planner/{swim(time_slot)}"
                if time_slot
                else None,
                redirect_text="Return to Planner",
            )
        if len(party.members) >= party.time_slot.event.max_party_size:
            raise AlertError(
                [Alert(alert_class="alert-error", message="Party is full.")],
                redirect_url=f"/event/{swim(party.time_slot.event)}/planner/{swim(time_slot)}",
                redirect_text="Return to Planner",
            )
        if user.id in [member.id for member in party.members]:
            raise AlertError(
                [Alert(alert_class="alert-warning", message="You are already a member of this party.")],
                redirect_url=f"/event/{swim(party.time_slot.event)}/planner/{swim(time_slot)}",
                redirect_text="Return to Planner",
            )

        party_user_link = PartyUserLink(user_id=user.id, party_id=party.id)
        transaction.add(party_user_link)

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
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        party_user_link = (
            await transaction.execute(
                select(PartyUserLink)
                .options(selectinload(PartyUserLink.party).selectinload(Party.members))
                .where(PartyUserLink.user_id == user.id, PartyUserLink.party.has(time_slot_id=time_slot.id))
            )
        ).scalar_one_or_none()

        if party_user_link is None:
            raise AlertError([Alert(alert_class="alert-warning", message="You are not in a party for this time slot.")])

        was_leader = party_user_link.is_leader

        await transaction.delete(party_user_link)

        if was_leader:
            # If the leader is the only member, delete the party
            await transaction.delete(party_user_link.party)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @get(
        path="/members/{time_slot_sqid:str}",
        dependencies={"time_slot": time_slot_with()},
    )
    async def get_party_members(
        self,
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> Template:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        party = (
            await transaction.execute(
                select(Party)
                .where(Party.time_slot_id == time_slot.id)
                .options(selectinload(Party.party_user_links), selectinload(Party.members))
                .where(Party.members.any(id=user.id))
            )
        ).scalar_one_or_none()

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
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
        member_sqid: Sqid,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        party_user_link = (
            await transaction.execute(
                select(PartyUserLink).where(
                    PartyUserLink.party.has(time_slot_id=time_slot.id), PartyUserLink.user_id == user.id
                )
            )
        ).scalar_one_or_none()

        if party_user_link is None or not party_user_link.is_leader:
            raise AlertError([Alert(alert_class="alert-error", message="You are not leading a party.")])

        member_id = sink(member_sqid)

        other_party_user_link = (
            await transaction.execute(
                select(PartyUserLink)
                .where(PartyUserLink.party.has(time_slot_id=time_slot.id), PartyUserLink.user_id == member_id)
                .options(
                    selectinload(PartyUserLink.user),
                )
            )
        ).scalar_one_or_none()

        if other_party_user_link is None:
            raise AlertError([Alert(alert_class="alert-error", message="Member not found in this party.")])

        # We need to use a nested transaction so we can force is_leader = False before setting the new leader
        # Otherwise we violate the unique constraint (well, index) on ix_unique_party_leader
        async with transaction.begin_nested():
            party_user_link.is_leader = False
            transaction.add(party_user_link)

        other_party_user_link.is_leader = True
        transaction.add(other_party_user_link)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/remove/{time_slot_sqid:str}/{member_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def remove_party_member(
        self,
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
        member_sqid: Sqid,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        if time_slot.status != TimeSlotStatus.PRE_ALLOCATION:
            return Redirect(f"/party/overview/{swim(time_slot)}")

        member_id = sink(member_sqid)

        if member_id == user.id:
            raise AlertError([Alert(alert_class="alert-error", message="You cannot remove yourself from the party.")])

        party_user_link = (
            await transaction.execute(
                select(PartyUserLink).where(
                    PartyUserLink.party.has(time_slot_id=time_slot.id), PartyUserLink.user_id == user.id
                )
            )
        ).scalar_one_or_none()

        if party_user_link is None or not party_user_link.is_leader:
            raise AlertError([Alert(alert_class="alert-error", message="You are not leading a party.")])

        other_party_user_link = (
            await transaction.execute(
                select(PartyUserLink)
                .where(PartyUserLink.party.has(time_slot_id=time_slot.id), PartyUserLink.user_id == member_id)
                .options(
                    selectinload(PartyUserLink.user),
                )
            )
        ).scalar_one_or_none()

        if other_party_user_link is None:
            raise AlertError([Alert(alert_class="alert-error", message="Member not found in this party.")])

        await transaction.delete(other_party_user_link)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/checkin/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def check_in(
        self,
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        existing_checkin = (
            await transaction.execute(
                select(UserCheckinStatus).where(
                    UserCheckinStatus.user_id == user.id, UserCheckinStatus.time_slot_id == time_slot.id
                )
            )
        ).scalar_one_or_none()

        if existing_checkin:
            existing_checkin.checked_in = True
            transaction.add(existing_checkin)
        else:
            new_checkin = UserCheckinStatus(user_id=user.id, time_slot_id=time_slot.id, checked_in=True)
            transaction.add(new_checkin)

        return Redirect(f"/party/overview/{swim(time_slot)}")

    @post(
        path="/checkout/{time_slot_sqid:str}",
        dependencies={
            "time_slot": time_slot_with(),
        },
    )
    async def check_out(
        self,
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> Template | Redirect:
        if time_slot is None:
            raise AlertError([Alert(alert_class="alert-error", message="Time slot not found.")])

        existing_checkin = (
            await transaction.execute(
                select(UserCheckinStatus).where(
                    UserCheckinStatus.user_id == user.id, UserCheckinStatus.time_slot_id == time_slot.id
                )
            )
        ).scalar_one_or_none()

        if existing_checkin:
            existing_checkin.checked_in = False
            transaction.add(existing_checkin)
        else:
            new_checkin = UserCheckinStatus(user_id=user.id, time_slot_id=time_slot.id, checked_in=False)
            transaction.add(new_checkin)

        return Redirect(f"/party/overview/{swim(time_slot)}")
