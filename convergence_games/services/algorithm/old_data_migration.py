from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import URL, create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

from convergence_games.db.models import (
    Base,
    Event,
    Game,
    Party,
    PartyUserLink,
    Session,
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


@dataclass
class OldGame:
    # AKA game
    id: int
    title: str
    minimum_players: int
    optimal_players: int
    maximum_players: int
    hidden: bool


@dataclass
class OldParty:
    # AKA adventuringgroup
    id: int
    time_slot_id: int
    checked_in: int
    pass


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


async def main() -> None:
    # Grab the old data:
    with old_engine.connect() as conn:
        old_users = [OldUser(id=row[0], name=row[1]) for row in conn.execute(text("SELECT id, name FROM person"))]
        old_sessions = [
            OldSession(id=row[0], time_slot_id=row[1], game_id=row[2])
            for row in conn.execute(text("SELECT id, time_slot_id, game_id FROM tableallocation"))
        ]
        old_games = [
            OldGame(
                id=row[0],
                title=row[1],
                minimum_players=row[2],
                optimal_players=row[3],
                maximum_players=row[4],
                hidden=row[5],
            )
            for row in conn.execute(
                text("SELECT id, title, minimum_players, optimal_players, maximum_players, hidden FROM game")
            )
        ]
        old_parties = [
            OldParty(id=row[0], time_slot_id=row[1], checked_in=row[2])
            for row in conn.execute(text("SELECT id, time_slot_id, checked_in FROM adventuringgroup"))
        ]
        old_user_game_preferences = [
            OldUserGamePreference(preference=row[0], party_id=row[1], session_id=row[2])
            for row in conn.execute(
                text("SELECT preference, adventuring_group_id, table_allocation_id FROM sessionpreference")
            )
        ]

    print(old_users)
    print(old_sessions)
    print(old_games)
    print(old_parties)
    print(old_user_game_preferences)

    async with new_engine.begin() as conn:
        # Create all metadata
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(main())
