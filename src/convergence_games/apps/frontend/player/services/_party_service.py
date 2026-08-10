import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from convergence_games.db.models import (
    Allocation,
    Event,
    Game,
    Party,
    PartyUserLink,
    Session,
    Table,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventD20Transaction,
)
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.ocean import Sqid, sink, sink_upper, swim


@dataclass(slots=True)
class PartyOverview:
    party: Party | None
    leader_id: int | None
    checked_in: bool
    is_gm: bool
    max_party_size: int | None
    allocated_session: Session | None
    allocated_session_players: list[User]


class PartyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def user_is_gm_for_time_slot(self, *, user_id: int, time_slot_id: int) -> bool:
        return (
            await self._session.execute(
                select(Session.id)
                .join(Game, Session.game_id == Game.id)
                .where(Session.time_slot_id == time_slot_id, Game.gamemaster_id == user_id, Session.committed)
                .limit(1)
            )
        ).scalar_one_or_none() is not None

    async def get_overview(self, *, user: User, time_slot: TimeSlot) -> PartyOverview:
        party = (
            await self._session.execute(
                select(Party)
                .where(Party.time_slot_id == time_slot.id)
                .where(Party.members.any(id=user.id))
                .options(
                    selectinload(Party.time_slot),
                    selectinload(Party.party_user_links),
                    selectinload(Party.members).options(
                        selectinload(User.checkin_statuses),
                        selectinload(User.latest_d20_transaction),
                    ),
                    with_loader_criteria(UserCheckinStatus, UserCheckinStatus.time_slot_id == time_slot.id),
                    with_loader_criteria(
                        UserEventD20Transaction, UserEventD20Transaction.event_id == time_slot.event_id
                    ),
                )
            )
        ).scalar_one_or_none()
        checked_in = (
            await self._session.execute(
                select(UserCheckinStatus.checked_in)
                .where(UserCheckinStatus.user_id == user.id)
                .where(UserCheckinStatus.time_slot_id == time_slot.id)
            )
        ).scalar_one_or_none() or False
        is_gm = await self.user_is_gm_for_time_slot(user_id=user.id, time_slot_id=time_slot.id)
        if party is None:
            leader_id = None
        else:
            leader_id = next((link.user_id for link in party.party_user_links if link.is_leader), None)
        max_party_size = (
            await self._session.execute(select(Event.max_party_size).where(Event.id == time_slot.event_id))
        ).scalar_one_or_none()

        self._session.expunge_all()
        allocated_session_stmt = (
            select(Session)
            .where(
                (Session.time_slot_id == time_slot.id)
                & (Session.committed)
                & (Session.allocations.any(party_leader_id=leader_id or user.id, committed=True))
            )
            .options(
                selectinload(Session.allocations)
                .selectinload(Allocation.party_leader)
                .selectinload(User.parties)
                .selectinload(Party.members),
                selectinload(Session.game).selectinload(Game.system),
                selectinload(Session.table).selectinload(Table.room),
                with_loader_criteria(Party, Party.time_slot_id == time_slot.id),
                with_loader_criteria(Allocation, Allocation.committed),
            )
        )
        allocated_session = (await self._session.execute(allocated_session_stmt)).scalar_one_or_none()
        allocated_session_players: list[User] = []
        if allocated_session:
            for allocation in allocated_session.allocations:
                allocated_party = allocation.party_leader.parties[0] if allocation.party_leader.parties else None
                if allocated_party:
                    allocated_session_players.extend(allocated_party.members)
                else:
                    allocated_session_players.append(allocation.party_leader)
        gm_index = (
            allocated_session_players.index(
                [p for p in allocated_session_players if p.id == allocated_session.game.gamemaster_id][0]
            )
            if allocated_session
            else None
        )
        if gm_index is not None:
            # Move the GM to the front of the list
            allocated_session_players.insert(0, allocated_session_players.pop(gm_index))

        return PartyOverview(
            party=party,
            leader_id=leader_id,
            checked_in=checked_in,
            is_gm=is_gm,
            max_party_size=max_party_size,
            allocated_session=allocated_session,
            allocated_session_players=allocated_session_players,
        )

    async def host_party(self, *, user_id: int, time_slot_id: int) -> Party:
        is_gm = await self.user_is_gm_for_time_slot(user_id=user_id, time_slot_id=time_slot_id)

        if is_gm:
            raise AlertError([Alert(alert_class="alert-error", message="GMs cannot host parties for their sessions.")])

        existing_party_for_time_slot = (
            await self._session.execute(
                select(Party).where(Party.time_slot_id == time_slot_id).where(Party.members.any(id=user_id))
            )
        ).scalar_one_or_none()

        if existing_party_for_time_slot:
            raise AlertError(
                [Alert(alert_class="alert-warning", message="You are already in a party for this time slot.")]
            )

        party = Party(
            time_slot_id=time_slot_id,
            created_by=user_id,
            updated_by=user_id,
            party_user_links=[PartyUserLink(user_id=user_id, is_leader=True)],
        )
        self._session.add(party)
        await self._session.flush()

        return party

    async def join_party(self, *, user_id: int, time_slot_id: int, invite_sqid: Sqid) -> Party:
        is_gm = await self.user_is_gm_for_time_slot(user_id=user_id, time_slot_id=time_slot_id)

        if is_gm:
            raise AlertError([Alert(alert_class="alert-error", message="GMs cannot join parties for their sessions.")])

        existing_party_user_link = (
            await self._session.execute(
                select(PartyUserLink).where(
                    PartyUserLink.user_id == user_id, PartyUserLink.party.has(time_slot_id=time_slot_id)
                )
            )
        ).scalar_one_or_none()

        if existing_party_user_link is not None:
            time_slot = (
                await self._session.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))
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
            await self._session.execute(
                select(Party)
                .where(Party.id == invite_id, Party.time_slot_id == time_slot_id)
                .options(selectinload(Party.members), selectinload(Party.time_slot).selectinload(TimeSlot.event))
            )
        ).scalar_one_or_none()

        # TODO: Tidy these up
        if party is None:
            time_slot = (
                await self._session.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))
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
                redirect_url=f"/event/{swim(party.time_slot.event)}/planner/{swim(party.time_slot)}",
                redirect_text="Return to Planner",
            )
        if user_id in [member.id for member in party.members]:
            raise AlertError(
                [Alert(alert_class="alert-warning", message="You are already a member of this party.")],
                redirect_url=f"/event/{swim(party.time_slot.event)}/planner/{swim(party.time_slot)}",
                redirect_text="Return to Planner",
            )

        party_user_link = PartyUserLink(user_id=user_id, party_id=party.id)
        self._session.add(party_user_link)

        return party

    async def leave_party(self, *, user_id: int, time_slot_id: int) -> None:
        party_user_link = (
            await self._session.execute(
                select(PartyUserLink)
                .options(selectinload(PartyUserLink.party).selectinload(Party.members))
                .where(PartyUserLink.user_id == user_id, PartyUserLink.party.has(time_slot_id=time_slot_id))
            )
        ).scalar_one_or_none()

        if party_user_link is None:
            raise AlertError([Alert(alert_class="alert-warning", message="You are not in a party for this time slot.")])

        was_leader = party_user_link.is_leader

        await self._session.delete(party_user_link)

        if was_leader:
            # If the leader is the only member, delete the party
            await self._session.delete(party_user_link.party)

    async def get_party_with_members(self, *, user_id: int, time_slot_id: int) -> Party | None:
        return (
            await self._session.execute(
                select(Party)
                .where(Party.time_slot_id == time_slot_id)
                .options(selectinload(Party.party_user_links), selectinload(Party.members))
                .where(Party.members.any(id=user_id))
            )
        ).scalar_one_or_none()

    async def promote_member(self, *, user_id: int, time_slot_id: int, member_sqid: Sqid) -> None:
        party_user_link = (
            await self._session.execute(
                select(PartyUserLink).where(
                    PartyUserLink.party.has(time_slot_id=time_slot_id), PartyUserLink.user_id == user_id
                )
            )
        ).scalar_one_or_none()

        if party_user_link is None or not party_user_link.is_leader:
            raise AlertError([Alert(alert_class="alert-error", message="You are not leading a party.")])

        member_id = sink(member_sqid)

        other_party_user_link = (
            await self._session.execute(
                select(PartyUserLink)
                .where(PartyUserLink.party.has(time_slot_id=time_slot_id), PartyUserLink.user_id == member_id)
                .options(
                    selectinload(PartyUserLink.user),
                )
            )
        ).scalar_one_or_none()

        if other_party_user_link is None:
            raise AlertError([Alert(alert_class="alert-error", message="Member not found in this party.")])

        # We need to use a nested transaction so we can force is_leader = False before setting the new leader
        # Otherwise we violate the unique constraint (well, index) on ix_unique_party_leader
        async with self._session.begin_nested():
            party_user_link.is_leader = False
            self._session.add(party_user_link)

        other_party_user_link.is_leader = True
        self._session.add(other_party_user_link)

    async def remove_member(self, *, user_id: int, time_slot_id: int, member_id: int) -> None:
        if member_id == user_id:
            raise AlertError([Alert(alert_class="alert-error", message="You cannot remove yourself from the party.")])

        party_user_link = (
            await self._session.execute(
                select(PartyUserLink).where(
                    PartyUserLink.party.has(time_slot_id=time_slot_id), PartyUserLink.user_id == user_id
                )
            )
        ).scalar_one_or_none()

        if party_user_link is None or not party_user_link.is_leader:
            raise AlertError([Alert(alert_class="alert-error", message="You are not leading a party.")])

        other_party_user_link = (
            await self._session.execute(
                select(PartyUserLink)
                .where(PartyUserLink.party.has(time_slot_id=time_slot_id), PartyUserLink.user_id == member_id)
                .options(
                    selectinload(PartyUserLink.user),
                )
            )
        ).scalar_one_or_none()

        if other_party_user_link is None:
            raise AlertError([Alert(alert_class="alert-error", message="Member not found in this party.")])

        await self._session.delete(other_party_user_link)

    async def check_in(self, *, user_id: int, time_slot_id: int, checkin_open_time: dt.datetime | None) -> None:
        if checkin_open_time is not None and dt.datetime.now(dt.UTC) < checkin_open_time:
            raise AlertError([Alert(alert_class="alert-warning", message="Check-in is not open yet for this session.")])

        await self._set_checkin_status(user_id=user_id, time_slot_id=time_slot_id, checked_in=True)

    async def check_out(self, *, user_id: int, time_slot_id: int) -> None:
        await self._set_checkin_status(user_id=user_id, time_slot_id=time_slot_id, checked_in=False)

    async def _set_checkin_status(self, *, user_id: int, time_slot_id: int, checked_in: bool) -> None:
        existing_checkin = (
            await self._session.execute(
                select(UserCheckinStatus).where(
                    UserCheckinStatus.user_id == user_id, UserCheckinStatus.time_slot_id == time_slot_id
                )
            )
        ).scalar_one_or_none()

        if existing_checkin:
            existing_checkin.checked_in = checked_in
            self._session.add(existing_checkin)
        else:
            new_checkin = UserCheckinStatus(user_id=user_id, time_slot_id=time_slot_id, checked_in=checked_in)
            self._session.add(new_checkin)


async def provide_party_service(transaction: AsyncSession) -> PartyService:
    return PartyService(transaction)
