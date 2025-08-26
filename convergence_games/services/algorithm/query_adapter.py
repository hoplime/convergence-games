"""
This module takes datastructures from the table and makes them into game allocator models
and vice versa to reinsert.
"""

from __future__ import annotations

import asyncio

from rich.pretty import pprint
from sqlalchemy import URL, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import aliased
from sqlalchemy.sql.functions import coalesce

from convergence_games.db.models import (
    Event,
    Game,
    Party,
    PartyUserLink,
    Session,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventCompensationTransaction,
)
from convergence_games.services.algorithm.models import AlgParty, AlgResult, AlgSession


async def adapt_to_inputs(transaction: AsyncSession, time_slot_id: int) -> tuple[list[AlgParty], list[AlgSession]]:
    # Checked in users and their (personal) preferences for this session
    checked_in_users_stmt = ()

    # Sessions
    Gamemaster = aliased(User)

    session_stmt = (
        select(
            Session.id,
            Game.player_count_minimum,
            Game.player_count_maximum,
            Game.player_count_maximum,
            Gamemaster.latest_compensation_transaction,
            Gamemaster.id,
        )
        .join(Game, Game.id == Session.game_id)
        .join(Gamemaster, Gamemaster.id == Game.gamemaster_id)
        .join(
            UserEventCompensationTransaction,
            (Gamemaster.id == UserEventCompensationTransaction.user_id),
            isouter=True,
        )
        .join(
            UserCheckinStatus,
            (Gamemaster.id == UserCheckinStatus.user_id) & (UserCheckinStatus.time_slot_id == time_slot_id),
            isouter=True,
        )
        .where(Session.time_slot_id == time_slot_id)
        .where(UserCheckinStatus.checked_in)
    )
    session_results = [r.tuple() for r in (await transaction.execute(session_stmt)).all()]
    alg_sessions = [
        AlgSession(
            session_id=r[0],
            min_players=r[1],
            opt_players=r[2],
            max_players=r[3],
            compensation=r[4].current_balance if r[4] is not None else 0,
            gm_party=AlgParty(
                party_id=("GM", r[5]),
                group_size=1,
                preferences=[],  # TODO
                total_compensation=r[4].current_balance if r[4] is not None else 0,
            ),
        )
        for r in session_results
    ]
    return [], alg_sessions


async def main() -> None:
    engine_url = URL.create(
        drivername="postgresql+asyncpg",
        username="MIGRATION_USER",
        password="MIGRATION_PASSWORD",
        host="localhost",
        port=5433,
        database="convergence",
    )
    engine = create_async_engine(engine_url)
    async with AsyncSession(engine) as session:
        async with session.begin():
            parties, sessions = await adapt_to_inputs(session, time_slot_id=1)
            pprint(parties)
            print(len(parties))
            pprint(sessions)
            print(len(sessions))


if __name__ == "__main__":
    asyncio.run(main())
