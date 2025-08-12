from __future__ import annotations

from typing import overload

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.alerts import Alert, alerts_response
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import Party, PartyUserLink, TimeSlot, User
from convergence_games.db.ocean import Sqid, sink


def party_with(*options: ExecutableOption, raise_404: bool = False) -> Provide:
    async def wrapper(
        transaction: AsyncSession,
        invite_code: str,
    ) -> Party | None:
        party = (
            await transaction.execute(select(Party).options(*options).where(Party.invite_code == invite_code))
        ).scalar_one_or_none()

        if not party and raise_404:
            raise HTTPException(status_code=404, detail="Party not found.")

        return party

    return Provide(wrapper)


class PartyController(Controller):
    path = "/party"
    guards = [user_guard]

    @get(
        path="/join/{invite_code:str}",
        dependencies={
            "party": party_with(
                selectinload(Party.time_slot).selectinload(TimeSlot.event),
            )
        },
    )
    async def join_party(
        self,
        request: Request,
        transaction: AsyncSession,
        party: Party | None,
        user: User,
    ) -> HTMXBlockTemplate:
        if party is None:
            return alerts_response([Alert(alert_class="alert-error", message="Party not found.")])
        if len(party.members) >= party.time_slot.event.max_party_size:
            return alerts_response([Alert(alert_class="alert-error", message="Party is full.")])
        if user.id in [member.id for member in party.members]:
            return alerts_response(
                [Alert(alert_class="alert-warning", message="You are already a member of this party.")]
            )

        party_user_link = PartyUserLink(user_id=user.id, party_id=party.id)
        transaction.add(party_user_link)

        return HTMXBlockTemplate(template_name="party/joined.html", context={"party": party})
