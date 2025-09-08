"""
This module takes datastructures from the table and makes them into game allocator models
and vice versa to reinsert.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from rich.pretty import pprint
from sqlalchemy import URL, Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import aliased, selectinload, with_loader_criteria

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import (
    Allocation,
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


def user_preferences_to_alg_preferences(
    preferences: list[UserGamePreference],
    has_d20: bool,
    session_results: list[tuple[SessionID, int, *tuple[Any, ...]]],
    already_played_games: set[int] | None = None,
) -> list[tuple[SessionID, tuple[UserGamePreferenceValue, bool]]]:
    if already_played_games is None:
        already_played_games = set()
    game_id_session_id_map: dict[int, SessionID] = {
        r_game_id: r_session_id for r_session_id, r_game_id, *_ in session_results
    }
    preference_map = {
        game_id_session_id_map[gp.game_id]: (
            (gp.preference if has_d20 else min(UserGamePreferenceValue.D12, gp.preference)),
            gp.game_id in already_played_games,
        )
        for gp in preferences
        if gp.game_id in game_id_session_id_map
    }
    alg_party_preferences = [
        (r_session_id, preference_map.get(r_session_id, (UserGamePreferenceValue.D6, False)))
        for r_session_id, *_ in session_results
    ]
    return alg_party_preferences


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
            Game.player_count_optimum,
            Game.player_count_maximum,
            Gamemaster,
        )
        # Include game and gamemaster of the session
        .join(Game, Game.id == Session.game_id)
        .join(Gamemaster, Gamemaster.id == Game.gamemaster_id)
        # Gamemaster is checked in
        .join(
            UserCheckinStatus,
            (Gamemaster.id == UserCheckinStatus.user_id) & (UserCheckinStatus.time_slot_id == time_slot_id),
        )
        .where(UserCheckinStatus.checked_in)
        # This time slot
        .where(Session.time_slot_id == time_slot_id)
        .where(Session.committed)
        .options(
            selectinload(Gamemaster.latest_compensation_transaction),
            selectinload(Gamemaster.latest_d20_transaction),
            selectinload(Gamemaster.all_game_preferences),
            selectinload(Gamemaster.games_played),
            with_loader_criteria(
                UserEventCompensationTransaction, UserEventCompensationTransaction.event_id == time_slot.event_id
            ),
            with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == time_slot.event_id),
            with_loader_criteria(UserGamePreference, UserGamePreference.frozen_at_time_slot_id == time_slot.id),
        )
    )
    session_results = [r.tuple() for r in (await transaction.execute(session_stmt)).all()]

    gm_user_ids_this_session_subq = (
        select(Game.gamemaster_id)
        .select_from(Session)
        .join(Game, (Session.time_slot_id == time_slot_id) & (Session.game_id == Game.id) & (Session.committed))
    )

    # House Keeping - If there are any GMs in parties they need to be removed
    # There hopefully shouldn't be any if we update the front end to prevent this!
    delete_gms_in_parties_stmt = delete(PartyUserLink).where(
        PartyUserLink.id.in_(
            select(PartyUserLink.id)
            .join(Party, Party.id == PartyUserLink.party_id)
            .where(
                PartyUserLink.user_id.in_(gm_user_ids_this_session_subq),
                Party.time_slot_id == time_slot_id,
            )
        )
    )
    delete_empty_parties_stmt = delete(Party).where(
        ~select(PartyUserLink).where(PartyUserLink.party_id == Party.id).exists()
    )
    aliased_party_user_link = aliased(PartyUserLink)
    # TODO: Verify this last query actually works
    party_links_to_reassign_leaders_stmt = (
        update(PartyUserLink)
        .where(
            PartyUserLink.id.in_(
                select(PartyUserLink.id)
                .where(
                    ~select(aliased_party_user_link)
                    .where(
                        PartyUserLink.party_id == aliased_party_user_link.party_id, aliased_party_user_link.is_leader
                    )
                    .exists()
                )
                .distinct(PartyUserLink.party_id)
            )
        )
        .values(is_leader=True)
    )
    _ = await transaction.execute(delete_gms_in_parties_stmt)
    _ = await transaction.execute(delete_empty_parties_stmt)
    _ = await transaction.execute(party_links_to_reassign_leaders_stmt)

    # Get checked in party leaders and their preferences
    party_subq = (
        select(Party, PartyUserLink)
        .join(Party, Party.id == PartyUserLink.party_id, isouter=True)
        .where(Party.time_slot_id == time_slot.id)
        .subquery()
    )
    party_alias = aliased(Party, party_subq)
    party_user_link_alias = aliased(PartyUserLink, party_subq)

    solo_players_and_leaders_stmt = cast(
        Select[tuple[User, Party | None]],
        (
            select(User, party_alias)
            .select_from(User)
            .join(party_subq, (party_user_link_alias.user_id == User.id), isouter=True)
            # Is checked in
            .join(
                UserCheckinStatus,
                (UserCheckinStatus.user_id == User.id) & (UserCheckinStatus.time_slot_id == time_slot.id),
            )
            .where(UserCheckinStatus.checked_in)
            # Leader or not in a party
            .where(party_user_link_alias.is_leader | (party_alias.id.is_(None)))
            # Not a GM
            .where(~User.id.in_(gm_user_ids_this_session_subq))
            .options(
                selectinload(User.latest_compensation_transaction),
                selectinload(User.latest_d20_transaction),
                selectinload(User.all_game_preferences),
                selectinload(User.games_played),
                selectinload(party_alias.members).options(
                    selectinload(User.latest_compensation_transaction),
                    selectinload(User.latest_d20_transaction),
                    selectinload(User.games_played),
                ),
                with_loader_criteria(
                    UserEventCompensationTransaction, UserEventCompensationTransaction.event_id == time_slot.event_id
                ),
                with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == time_slot.event_id),
                with_loader_criteria(UserGamePreference, UserGamePreference.frozen_at_time_slot_id == time_slot.id),
            )
        ),
    )
    party_results: list[tuple[User, Party | None]] = [
        r.tuple() for r in (await transaction.execute(solo_players_and_leaders_stmt)).all()
    ]

    # Construct the final alg results
    def _alg_party_from_party_query(party_leader: User, party: Party | None) -> AlgParty:
        preferences_to_use = party_leader.all_game_preferences
        party_leader_id = ("USER", party_leader.id)
        if party is not None:
            has_d20 = all(
                member.latest_d20_transaction.current_balance > 0
                if member.latest_d20_transaction is not None
                else False
                for member in party.members
            )
            total_compensation = sum(
                member.latest_compensation_transaction.current_balance
                if member.latest_compensation_transaction is not None
                else 0
                for member in party.members
            )
            group_size = len(party.members)
        else:
            has_d20 = (
                party_leader.latest_d20_transaction is not None
                and party_leader.latest_d20_transaction.current_balance > 0
            )
            total_compensation = (
                party_leader.latest_compensation_transaction.current_balance
                if party_leader.latest_compensation_transaction is not None
                else 0
            )
            group_size = 1
        # Already played
        already_played_games = {gp.game_id for gp in party_leader.games_played if not gp.allow_play_again}
        if party is not None:
            for member in party.members:
                already_played_games.update({gp.game_id for gp in member.games_played if not gp.allow_play_again})

        return AlgParty(
            party_leader_id=party_leader_id,
            group_size=group_size,
            preferences=user_preferences_to_alg_preferences(
                preferences_to_use, has_d20, session_results, already_played_games
            ),
            total_compensation=total_compensation,
        )

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
                party_leader_id=("GM", r_gm.id),
                group_size=1,
                preferences=user_preferences_to_alg_preferences(
                    r_gm.all_game_preferences,
                    r_gm.latest_d20_transaction.current_balance > 0
                    if r_gm.latest_d20_transaction is not None
                    else False,
                    session_results,
                    {gp.game_id for gp in r_gm.games_played if not gp.allow_play_again},
                ),
                total_compensation=comp,
            ),
        )
        for r_session_id, r_game_id, r_min_players, r_opt_player, r_max_players, r_gm in session_results
    ]
    alg_parties = [_alg_party_from_party_query(*r) for r in party_results]

    return alg_sessions, alg_parties


async def adapt_results_to_database(
    transaction: AsyncSession,
    time_slot_id: int,
    alg_results: list[AlgResult],
    compensation: Compensation,
) -> None:
    print(time_slot_id)
    print(alg_results)
    print(compensation)

    _ = await transaction.execute(delete(Allocation).where(Allocation.session.has(time_slot_id=time_slot_id)))

    new_allocations: list[Allocation] = []
    for alg_result in alg_results:
        party_type, party_leader_id = alg_result.party_leader_id
        if party_type == "OVERFLOW":
            continue

        if alg_result.session_id is None:
            print("SOMEONE ENDED UP IN OVERFLOW TODO!")
            continue

        new_allocations.append(
            Allocation(
                committed=False,
                party_leader_id=party_leader_id,
                session_id=alg_result.session_id,
            )
        )

    transaction.add_all(new_allocations)

    # TODO: Compensation
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
