from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import URL, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import (
    Base,
    Event,
    Game,
    Party,
    PartyUserLink,
    Room,
    Session,
    System,
    Table,
    TimeSlot,
    User,
    UserCheckinStatus,
    UserEventD20Transaction,
    UserGamePreference,
)

# This script takes in last year's data and converts it to this year's database format
# So that we can evaluate the new allocation algorithm against real user data

# Make a connection to the backup of the prod database
# This .db is ignored because it contains sensitive information like emails and people's preferences
old_engine = create_engine("sqlite:///prod.db")
new_engine_url = URL.create(
    drivername="postgresql+asyncpg",
    username="MIGRATION_USER",
    password="MIGRATION_PASSWORD",
    host="localhost",
    port=5433,
    database="convergence",
)
new_engine = create_async_engine(new_engine_url)


@dataclass
class OldSession:
    # AKA tableallocation
    id: int
    time_slot_id: int
    game_id: int
    table_id: int


@dataclass
class OldGame:
    # AKA game
    id: int
    title: str
    minimum_players: int
    optimal_players: int
    maximum_players: int
    gamemaster_id: int


@dataclass
class OldParty:
    # AKA adventuringgroup
    id: int
    time_slot_id: int
    checked_in: bool


@dataclass
class OldUser:
    # AKA person
    id: int
    name: str


@dataclass
class OldUserGamePreference:
    # AKA sessionpreference
    preference: int
    party_id: int  # adventuring_group_id
    session_id: int  # table_allocation_id


@dataclass
class OldPartyUserLink:
    party_id: int  # adventuring_group_id
    user_id: int  # person_id


async def main(time_slot_id: int = 1) -> None:
    # Grab the old data:
    with old_engine.connect() as conn:
        old_users = [OldUser(id=row[0], name=row[1]) for row in conn.execute(text("SELECT id, name FROM person"))]
        old_sessions = [
            OldSession(id=row[0], time_slot_id=row[1], game_id=row[2], table_id=row[3])
            for row in conn.execute(text("SELECT id, time_slot_id, game_id, table_id FROM tableallocation"))
        ]
        old_games = [
            OldGame(
                id=row[0],
                title=row[1],
                minimum_players=row[2],
                optimal_players=row[3],
                maximum_players=row[4],
                gamemaster_id=row[5],
            )
            for row in conn.execute(
                text(
                    "SELECT id, title, minimum_players, optimal_players, maximum_players, gamemaster_id FROM game WHERE hidden = false"
                )
            )
        ]
        old_parties = [
            OldParty(id=row[0], time_slot_id=row[1], checked_in=row[2])
            for row in conn.execute(text("SELECT id, time_slot_id, checked_in FROM adventuringgroup"))
        ]
        old_party_user_links = [
            OldPartyUserLink(party_id=row[0], user_id=row[1])
            for row in conn.execute(text("SELECT adventuring_group_id, member_id FROM personadventuringgrouplink"))
        ]
        old_user_game_preferences = [
            OldUserGamePreference(preference=row[0], party_id=row[1], session_id=row[2])
            for row in conn.execute(
                text(
                    "SELECT preference, adventuring_group_id, table_allocation_id FROM sessionpreference JOIN adventuringgroup ON sessionpreference.adventuring_group_id = adventuringgroup.id WHERE adventuringgroup.time_slot_id = :tsid"
                ),
                {"tsid": time_slot_id},
            )
        ]
        old_parties_which_used_d20s_in_this_time_slot: set[int] = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT DISTINCT adventuring_group_id FROM sessionpreference JOIN tableallocation ON sessionpreference.table_allocation_id = tableallocation.id WHERE tableallocation.time_slot_id = :tsid AND sessionpreference.preference = 20"
                ),
                {"tsid": time_slot_id},
            )
        }

    print(old_users)
    print(old_games)
    print(old_sessions)
    print(old_parties)
    print(old_party_user_links)
    print(old_user_game_preferences)

    async with new_engine.begin() as conn:
        # Create all metadata
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create relevant stuff
    event = Event(
        name="Migration Event",
        start_date=datetime(2024, 9, 7, tzinfo=timezone.utc),
        end_date=datetime(2024, 9, 8, tzinfo=timezone.utc),
        rooms=[
            Room(
                name="Migration Room",
                tables=[
                    Table(name=f"Table {i}")
                    for i in range(500)  # arbitrary number of tables tbh
                ],
            )
        ],
        time_slots=[
            TimeSlot(
                id=i + 1,
                name=f"Time Slot {i}",
                start_time=datetime(2024, 9, 7, 9, 0, tzinfo=timezone.utc),
                end_time=datetime(2024, 9, 7, 10, 0, tzinfo=timezone.utc),
                checkin_open_time=None,
            )
            for i in range(5)
        ],
    )
    system = System(name="Migration System")

    # Create imported users
    new_objects: list[Base] = [event]

    for old_user in old_users:
        new_user = User(
            first_name=old_user.name,
            last_name="",
            id=old_user.id,
            over_18=True,  # Assume yes
        )
        new_objects.append(new_user)

    for old_game in old_games:
        new_game = Game(
            id=old_game.id,
            name=old_game.title,
            gamemaster_id=old_game.gamemaster_id,
            player_count_minimum=old_game.minimum_players,
            player_count_optimum=old_game.optimal_players,
            player_count_maximum=old_game.maximum_players,
            event=event,
            system=system,
            submission_status="APPROVED",
        )
        new_objects.append(new_game)

    session_game_map = {old_session.id: old_session.game_id for old_session in old_sessions}
    for old_session in old_sessions:
        if old_session.game_id not in [old_game.id for old_game in old_games]:
            # This game was hidden, so skip it
            continue
        new_session = Session(
            committed=True,
            game_id=old_session.game_id,
            table_id=old_session.table_id,
            time_slot_id=old_session.time_slot_id,
            event=event,
        )
        new_objects.append(new_session)

    old_parties_by_id: dict[int, OldParty] = {old_party.id: old_party for old_party in old_parties}
    party_member_counts = {
        old_party.id: sum(1 for p in old_party_user_links if p.party_id == old_party.id) for old_party in old_parties
    }
    excluded_single_parties: set[int] = set()
    for old_party in old_parties:
        # For 3/4 of single person parties, don't make them parties! They need to be individuals
        if party_member_counts[old_party.id] == 1 and old_party.id % 4 != 0:
            excluded_single_parties.add(old_party.id)
            # print("EXCLUDING", old_party.id)
            continue

        new_party = Party(
            id=old_party.id,
            time_slot_id=old_party.time_slot_id,
        )
        new_objects.append(new_party)

    already_inserted_party_ids: set[int] = set()
    for old_party_user_link in old_party_user_links:
        # Always set the checkin
        new_user_checkin_status = UserCheckinStatus(
            checked_in=old_parties_by_id[old_party_user_link.party_id].checked_in,
            user_id=old_party_user_link.user_id,
            time_slot_id=old_parties_by_id[old_party_user_link.party_id].time_slot_id,
        )
        new_objects.append(new_user_checkin_status)

        # Always set the D20 transactions
        if old_party_user_link.party_id in old_parties_which_used_d20s_in_this_time_slot:
            new_d20_transaction = UserEventD20Transaction(
                current_balance=1,  # Assume they had none before
                delta=1,
                user_id=old_party_user_link.user_id,
                event=event,
            )
            new_objects.append(new_d20_transaction)

        if old_party_user_link.party_id not in excluded_single_parties:
            new_party_user_link = PartyUserLink(
                party_id=old_party_user_link.party_id,
                user_id=old_party_user_link.user_id,
                is_leader=old_party_user_link.party_id not in already_inserted_party_ids,
            )
            new_objects.append(new_party_user_link)
        already_inserted_party_ids.add(old_party_user_link.party_id)

    # Adding preferences to all party members, though only solos or the leaders should matter
    for old_user_game_preference in old_user_game_preferences:
        party_members = [
            link.user_id for link in old_party_user_links if link.party_id == old_user_game_preference.party_id
        ]
        for party_member in party_members:
            new_user_game_preference = UserGamePreference(
                user_id=party_member,
                game_id=session_game_map[old_user_game_preference.session_id],
                preference=UserGamePreferenceValue(
                    {
                        0: 0,
                        1: 4,
                        2: 6,
                        3: 8,
                        4: 10,
                        5: 12,
                        20: 20,
                    }[old_user_game_preference.preference]
                ),
            )
            new_objects.append(new_user_game_preference)

    # Add all new objects
    async with AsyncSession(new_engine) as session:
        async with session.begin():
            session.add_all(new_objects)
            await session.commit()

    await new_engine.dispose()

    print("Migration complete.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--time-slot-id", "-t", type=int, default=1)
    parser.add_argument("--just-create", action="store_true")
    args = parser.parse_args()

    if args.just_create:
        print("Just creating metadata...")

        async def create_metadata_only() -> None:
            async with new_engine.begin() as conn:
                # await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
            await new_engine.dispose()
            print("Metadata creation complete.")

        asyncio.run(create_metadata_only())
    else:
        asyncio.run(main(args.time_slot_id))
