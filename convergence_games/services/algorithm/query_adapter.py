"""
This module takes datastructures from the table and makes them into game allocator models
and vice versa to reinsert.
"""

from __future__ import annotations

import asyncio
from typing import cast

from rich.pretty import pprint
from sqlalchemy import URL, exists, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import (
    Game,
    Party,
    PartyUserLink,
    Session,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventCompensationTransaction,
    UserEventD20Transaction,
    UserGamePreference,
)
from convergence_games.services.algorithm.game_allocator import Compensation
from convergence_games.services.algorithm.models import AlgParty, AlgResult, AlgSession, SessionID


async def adapt_to_inputs(transaction: AsyncSession, time_slot_id: int) -> tuple[list[AlgSession], list[AlgParty]]:
    time_slot = (await transaction.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))).scalar_one_or_none()

    if time_slot is None:
        raise ValueError(f"TimeSlot with id {time_slot_id} does not exist.")

    # Sessions
    Gamemaster = aliased(User)

    session_stmt = (
        select(
            Session.id,
            Game.id,
            Game.player_count_minimum,
            Game.player_count_maximum,
            Game.player_count_maximum,
            Gamemaster,
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
        .options(
            selectinload(Gamemaster.latest_compensation_transaction),
            selectinload(Gamemaster.latest_d20_transaction),
            selectinload(Gamemaster.game_preferences),
            with_loader_criteria(
                UserEventCompensationTransaction, UserEventCompensationTransaction.event_id == time_slot.event_id
            ),
            with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == time_slot.event_id),
        )
    )
    session_results = [r.tuple() for r in (await transaction.execute(session_stmt)).all()]
    game_id_session_id_map: dict[int, SessionID] = {
        r_game_id: r_session_id for r_session_id, r_game_id, *_ in session_results
    }

    # Checked in users and their (personal) preferences for this session
    PLinkThisUser = aliased(PartyUserLink)
    PartyLeader = aliased(User)

    # TODO: Pop GMs from member lists so they're in parties by themselves?
    checked_in_solo_or_leaders_stmt = (
        select(User, Party, PartyLeader)
        .select_from(User)
        .where(
            exists(UserCheckinStatus.id).where(
                (UserCheckinStatus.user_id == User.id)
                & (UserCheckinStatus.time_slot_id == time_slot_id)
                & (UserCheckinStatus.checked_in)
            )
        )
        .join(
            PLinkThisUser,
            (PLinkThisUser.user_id == User.id) & (PLinkThisUser.party.has(time_slot_id=time_slot_id)),
            isouter=True,
        )
        .join(Party, Party.id == PLinkThisUser.party_id, isouter=True)
        # .join(PLinkAllInParty, PLinkAllInParty.party_id == Party.id, isouter=True)
        .join(PartyLeader, (PartyLeader.party_user_links.any(party_id=Party.id, is_leader=True)), isouter=True)
        .where((PartyLeader.id == User.id) | (PartyLeader.id.is_(None)))
        .options(
            selectinload(PartyLeader.game_preferences),
            selectinload(User.game_preferences),
            selectinload(User.latest_compensation_transaction),
            selectinload(User.latest_d20_transaction),
            selectinload(Party.members).options(
                selectinload(User.latest_compensation_transaction),
                selectinload(User.latest_d20_transaction),
            ),
        )
    )
    party_results: list[tuple[User, Party | None, User | None]] = [
        r.tuple() for r in (await transaction.execute(checked_in_solo_or_leaders_stmt)).all()
    ]

    # Construct the final alg results
    def _alg_party_from_party_query(user: User, party: Party | None, party_leader: User | None) -> AlgParty:
        if party is not None and party_leader is not None:
            has_d20 = all(
                member.latest_d20_transaction.current_balance > 0
                if member.latest_d20_transaction is not None
                else False
                for member in party.members
            )
            preferences_to_use = party_leader.game_preferences
            party_id = ("PARTY", party.id)
            group_size = len(party.members)
        else:
            has_d20 = user.latest_d20_transaction is not None and user.latest_d20_transaction.current_balance > 0
            preferences_to_use = user.game_preferences
            party_id = ("USER", user.id)
            group_size = 1

        return AlgParty(
            party_id=party_id,
            group_size=group_size,
            preferences=_user_preferences_to_alg_preferences(preferences_to_use, has_d20),
            total_compensation=user.latest_compensation_transaction.current_balance
            if user.latest_compensation_transaction is not None
            else 0,
        )

    def _user_preferences_to_alg_preferences(
        preferences: list[UserGamePreference], has_d20: bool
    ) -> list[tuple[SessionID, UserGamePreferenceValue]]:
        preference_map = {
            game_id_session_id_map[gp.game_id]: (
                gp.preference if has_d20 else min(UserGamePreferenceValue.D12, gp.preference)
            )
            for gp in preferences
        }
        alg_party_preferences = [
            (cast(SessionID, r_session_id), preference_map.get(r_session_id, UserGamePreferenceValue.D6))
            for r_session_id, *_ in session_results
        ]
        return alg_party_preferences

    alg_sessions = [
        AlgSession(
            session_id=r_session_id,
            min_players=r_min_players,
            opt_players=r_opt_player,
            max_players=r_max_players,
            compensation=(
                comp := r_gm.latest_compensation_transaction.current_balance
                if r_gm.latest_compensation_transaction is not None
                else 0
            ),
            gm_party=AlgParty(
                party_id=("GM", r_gm.id),
                group_size=1,
                preferences=_user_preferences_to_alg_preferences(
                    r_gm.game_preferences,
                    r_gm.latest_d20_transaction.current_balance > 0
                    if r_gm.latest_d20_transaction is not None
                    else False,
                ),
                total_compensation=comp,
            ),
        )
        for r_session_id, r_game_id, r_min_players, r_opt_player, r_max_players, r_gm in session_results
    ]
    alg_parties = [_alg_party_from_party_query(*r) for r in party_results]

    return alg_sessions, alg_parties


async def adapt_results_to_database(
    transaction: AsyncSession, time_slot_id: int, alg_results: list[AlgResult], compensation: Compensation
) -> None:
    print(time_slot_id)
    print(alg_results)
    print(compensation)
    pass


async def main() -> None:
    engine_url = URL.create(
        drivername="postgresql+asyncpg",
        username="MIGRATION_USER",
        password="MIGRATION_PASSWORD",
        host="localhost",
        port=5433,
        database="convergence",
    )
    engine = create_async_engine(engine_url, echo=True)
    async with AsyncSession(engine) as session:
        async with session.begin():
            parties, sessions = await adapt_to_inputs(session, time_slot_id=1)
            pprint(parties)
            print(len(parties))
            pprint(sessions)
            print(len(sessions))


if __name__ == "__main__":
    asyncio.run(main())
