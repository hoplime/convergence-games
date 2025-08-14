from __future__ import annotations

import time
from typing import overload

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.alerts import Alert, alerts_response
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import Party, PartyUserLink, TimeSlot, User
from convergence_games.db.ocean import Sqid, sink, sink_upper, swim, swim_upper


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
    ) -> HTMXBlockTemplate:
        if time_slot is None:
            return alerts_response([Alert(alert_class="alert-error", message="Time slot not found.")])

        existing_party_for_time_slot = (
            await transaction.execute(
                select(Party).where(Party.time_slot_id == time_slot.id).where(Party.members.any(id=user.id))
            )
        ).scalar_one_or_none()

        if existing_party_for_time_slot:
            return alerts_response(
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
        invite_sqid = swim_upper(party)

        return alerts_response(
            [Alert(alert_class="alert-info", message=f"You created a new party with invite code {invite_sqid}.")]
        )

    @get(path="/join")
    async def join_empty_party(self, request: Request) -> Template:
        return alerts_response([Alert(alert_class="alert-error", message="No party found with that code.")], request)

    @get(
        path="/join/{invite_sqid:str}",
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
        party: Party | None,
        user: User,
        request: Request,
    ) -> HTMXBlockTemplate:
        if party is None:
            return alerts_response(
                [Alert(alert_class="alert-error", message="No party found with that code.")], request
            )
        if len(party.members) >= party.time_slot.event.max_party_size:
            return alerts_response([Alert(alert_class="alert-error", message="Party is full.")], request)
        if user.id in [member.id for member in party.members]:
            return alerts_response(
                [Alert(alert_class="alert-warning", message="You are already a member of this party.")], request
            )

        party_user_link = PartyUserLink(user_id=user.id, party_id=party.id)
        transaction.add(party_user_link)

        return alerts_response(
            [Alert(alert_class="alert-success", message="You have joined the party successfully.")], request
        )

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
    ) -> HTMXBlockTemplate:
        if time_slot is None:
            return alerts_response([Alert(alert_class="alert-error", message="Time slot not found.")])

        party_user_link = (
            await transaction.execute(
                select(PartyUserLink)
                .options(selectinload(PartyUserLink.party).selectinload(Party.members))
                .where(PartyUserLink.user_id == user.id, PartyUserLink.party.has(time_slot_id=time_slot.id))
            )
        ).scalar_one_or_none()

        if party_user_link is None:
            return alerts_response(
                [Alert(alert_class="alert-warning", message="You are not in a party for this time slot.")]
            )

        if party_user_link.is_leader and len(party_user_link.party.members) > 1:
            return alerts_response(
                [
                    Alert(
                        alert_class="alert-error",
                        message="You cannot leave a party you are leading that still has other members - choose a new leader!",
                    )
                ]
            )

        was_leader = party_user_link.is_leader

        await transaction.delete(party_user_link)

        if was_leader:
            # If the leader is the only member, delete the party
            await transaction.delete(party_user_link.party)

        return alerts_response([Alert(alert_class="alert-success", message="You have left the party successfully.")])

    @get(
        path="/members/{time_slot_sqid:str}",
        dependencies={"time_slot": time_slot_with()},
    )
    async def get_party_members(
        self,
        transaction: AsyncSession,
        user: User,
        time_slot: TimeSlot | None,
    ) -> HTMXBlockTemplate:
        if time_slot is None:
            return alerts_response([Alert(alert_class="alert-error", message="Time slot not found.")])

        party = (
            await transaction.execute(
                select(Party)
                .where(Party.time_slot_id == time_slot.id)
                .options(selectinload(Party.party_user_links), selectinload(Party.members))
                .where(Party.members.any(id=user.id))
            )
        ).scalar_one_or_none()

        if party is None:
            return alerts_response([Alert(alert_class="alert-warning", message="No party found for this time slot.")])

        return alerts_response(
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
    ) -> HTMXBlockTemplate:
        if time_slot is None:
            return alerts_response([Alert(alert_class="alert-error", message="Time slot not found.")])

        party_user_link = (
            await transaction.execute(
                select(PartyUserLink).where(
                    PartyUserLink.party.has(time_slot_id=time_slot.id), PartyUserLink.user_id == user.id
                )
            )
        ).scalar_one_or_none()

        if party_user_link is None or not party_user_link.is_leader:
            return alerts_response([Alert(alert_class="alert-error", message="You are not leading a party.")])

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
            return alerts_response([Alert(alert_class="alert-error", message="Member not found in this party.")])

        # We need to use a nested transaction so we can force is_leader = False before setting the new leader
        # Otherwise we violate the unique constraint (well, index) on ix_unique_party_leader
        async with transaction.begin_nested():
            party_user_link.is_leader = False
            transaction.add(party_user_link)

        other_party_user_link.is_leader = True
        transaction.add(other_party_user_link)

        return alerts_response(
            [
                Alert(
                    alert_class="alert-success",
                    message=f"{other_party_user_link.user.full_name} has been promoted to leader of the party.",
                )
            ]
        )

    @get(path="/whoami")
    async def whoami(
        self,
        user: User,
    ) -> HTMXBlockTemplate:
        return alerts_response([Alert(alert_class="alert-info", message=swim(user))])
