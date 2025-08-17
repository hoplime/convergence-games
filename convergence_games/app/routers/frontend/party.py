from __future__ import annotations

import time
from typing import cast, overload

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from litestar.response import Redirect
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import query, selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.alerts import Alert, AlertError
from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import Event, Party, PartyUserLink, TimeSlot, User
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
                    selectinload(Party.members),
                )
            )
        ).scalar_one_or_none()
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
            "party": party_with(
                selectinload(Party.time_slot).selectinload(TimeSlot.event),
                selectinload(Party.members),
            )
        },
    )
    async def join_party(
        self,
        transaction: AsyncSession,
        user: User,
        request: Request,
        time_slot_sqid: Sqid,
        invite_sqid: Sqid,
    ) -> Template | Redirect:
        time_slot_id = sink(time_slot_sqid)

        # existing_party_user_link = (
        #     await transaction.execute(
        #         select(PartyUserLink)
        #         .options(selectinload(PartyUserLink.party).selectinload(Party.members))
        #         .where(PartyUserLink.user_id == user.id, PartyUserLink.party.has(time_slot_id=time_slot_id))
        #     )
        # ).scalar_one_or_none()

        # if existing_party_user_link is not None:
        #     raise AlertError(
        #         [Alert(alert_class="alert-warning", message="You are already in a party for this time slot.")]
        #     )

        try:
            invite_id = sink_upper(invite_sqid)
        except Exception as e:
            raise AlertError([Alert(alert_class="alert-error", message="Invalid invite code.")]) from e

        party = (
            await transaction.execute(
                select(Party)
                .where(Party.id == invite_id, Party.time_slot_id == time_slot_id)
                .options(selectinload(Party.members), selectinload(Party.time_slot).selectinload(TimeSlot.event))
            )
        ).scalar_one_or_none()

        if party is None:
            raise AlertError([Alert(alert_class="alert-error", message="No party found with that code.")])
        if len(party.members) >= party.time_slot.event.max_party_size:
            raise AlertError([Alert(alert_class="alert-error", message="Party is full.")])
        if user.id in [member.id for member in party.members]:
            raise AlertError([Alert(alert_class="alert-warning", message="You are already a member of this party.")])

        party_user_link = PartyUserLink(user_id=user.id, party_id=party.id)
        transaction.add(party_user_link)

        if not request.htmx:
            # This is from a QRCode - go to the overall planner view
            return Redirect(f"/event/{swim(party.time_slot.event)}/planner/{time_slot_sqid}")

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

    @get(path="/whoami")
    async def whoami(
        self,
        user: User,
    ) -> Template:
        raise AlertError([Alert(alert_class="alert-info", message=swim(user))])
