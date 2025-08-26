from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import URL, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

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
    UserGamePreference,
    UserGamePreferenceValue,
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
    hidden: bool
    gamemaster_id: int


@dataclass
class OldParty:
    # AKA adventuringgroup
    id: int
    time_slot_id: int


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


async def main() -> None:
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
                hidden=row[5],
                gamemaster_id=row[6],
            )
            for row in conn.execute(
                text(
                    "SELECT id, title, minimum_players, optimal_players, maximum_players, hidden, gamemaster_id FROM game"
                )
            )
        ]
        old_parties = [
            OldParty(id=row[0], time_slot_id=row[1])
            for row in conn.execute(text("SELECT id, time_slot_id FROM adventuringgroup WHERE checked_in = true"))
        ]
        old_party_user_links = [
            OldPartyUserLink(party_id=row[0], user_id=row[1])
            for row in conn.execute(text("SELECT adventuring_group_id, member_id FROM personadventuringgrouplink"))
        ]
        old_user_game_preferences = [
            OldUserGamePreference(preference=row[0], party_id=row[1], session_id=row[2])
            for row in conn.execute(
                text("SELECT preference, adventuring_group_id, table_allocation_id FROM sessionpreference")
            )
        ]

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
    new_objects: list[Event | User | Game | Session | PartyUserLink | Party | UserGamePreference] = [event]

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
        )
        new_objects.append(new_game)

    for old_session in old_sessions:
        new_session = Session(
            committed=True,
            game_id=old_session.game_id,
            table_id=old_session.table_id,
            time_slot_id=old_session.time_slot_id,
            event=event,
        )
        new_objects.append(new_session)

    for old_party in old_parties:
        new_party = Party(
            id=old_party.id,
            time_slot_id=old_party.time_slot_id,
        )
        new_objects.append(new_party)

    for old_party_user_link in old_party_user_links:
        if old_party_user_link.party_id not in [old_party.id for old_party in old_parties]:
            # This party wasn't checked in, so skip it
            continue
        new_party_user_link = PartyUserLink(
            party_id=old_party_user_link.party_id,
            user_id=old_party_user_link.user_id,
        )
        new_objects.append(new_party_user_link)

    # Add all new objects
    async with AsyncSession(new_engine) as session:
        async with session.begin():
            session.add_all(new_objects)
            await session.commit()

    await new_engine.dispose()

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
