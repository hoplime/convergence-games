"""Create a mock Convergence 2026 event with rooms, tables, and time slots.

Usage:
    PYTHONPATH=. python scripts/create_mock_event.py

Idempotent: if an event named "Convergence 2026" already exists, skips creation
and prints the existing event ID.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.db.enums import RoomFacility, TableFacility, TableSize
from convergence_games.db.models import Event, Room, Table, TimeSlot
from convergence_games.settings import SETTINGS

EVENT_NAME = "Convergence 2026"
NZT = ZoneInfo("Pacific/Auckland")


def build_event() -> Event:
    """Build the Convergence 2026 event with all nested rooms, tables, and time slots."""
    return Event(
        name=EVENT_NAME,
        description="",
        start_date=dt.datetime(2026, 9, 12, tzinfo=NZT),
        end_date=dt.datetime(2026, 9, 13, tzinfo=NZT),
        timezone="Pacific/Auckland",
        max_party_size=3,
        rooms=[
            Room(
                name="Sigil",
                description="The Central Meeting Room",
                facilities=RoomFacility.NONE,
            ),
            Room(
                name="Golarian",
                description="Room 1",
                facilities=RoomFacility.NONE,
                tables=[
                    Table(
                        name="01",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.WHITEBOARD,
                    ),
                    Table(
                        name="02",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.EXTRA_SIDETABLE,
                    ),
                    Table(
                        name="03",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.WHITEBOARD,
                    ),
                    Table(name="04", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(name="05", size=TableSize.SMALL, facilities=TableFacility.NONE),
                    Table(name="06", size=TableSize.SMALL, facilities=TableFacility.EXTRA_SIDETABLE),
                    Table(name="07", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(name="08", size=TableSize.SMALL, facilities=TableFacility.NONE),
                    Table(
                        name="09",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.EXTRA_SIDETABLE,
                    ),
                ],
            ),
            Room(
                name="Eberron",
                description="Room 2",
                facilities=RoomFacility.NONE,
                tables=[
                    Table(name="11", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(
                        name="12",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.EXTRA_SIDETABLE,
                    ),
                    Table(name="13", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(name="14", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(name="15", size=TableSize.SMALL, facilities=TableFacility.NONE),
                    Table(name="16", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(
                        name="17",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.EXTRA_SIDETABLE,
                    ),
                    Table(name="18", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                ],
            ),
            Room(
                name="Doskvol",
                description="Room 3",
                facilities=RoomFacility.NONE,
                tables=[
                    Table(name="21", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(name="22", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(name="23", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(name="24", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(name="25", size=TableSize.SMALL, facilities=TableFacility.NONE),
                    Table(name="26", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(
                        name="27",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET
                        | TableFacility.WHITEBOARD
                        | TableFacility.EXTRA_SIDETABLE,
                    ),
                    Table(name="28", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                ],
            ),
            Room(
                name="Arkham",
                description="Room 4",
                facilities=RoomFacility.NONE,
                tables=[
                    Table(
                        name="31",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.EXTRA_SIDETABLE,
                    ),
                    Table(name="32", size=TableSize.LARGE, facilities=TableFacility.POWER_OUTLET),
                    Table(name="33", size=TableSize.LARGE, facilities=TableFacility.NONE),
                    Table(name="34", size=TableSize.SMALL, facilities=TableFacility.NONE),
                    Table(name="35", size=TableSize.SMALL, facilities=TableFacility.POWER_OUTLET),
                    Table(
                        name="36",
                        size=TableSize.LARGE,
                        facilities=TableFacility.POWER_OUTLET
                        | TableFacility.WHITEBOARD
                        | TableFacility.EXTRA_SIDETABLE,
                    ),
                ],
            ),
            Room(
                name="The Lonely Mountain",
                description="Room 5",
                facilities=RoomFacility.NONE,
            ),
            Room(
                name="Zhodani Consulate",
                description="Side Room 1",
                facilities=RoomFacility.QUIET | RoomFacility.PRIVATE,
                tables=[
                    Table(
                        name="41",
                        size=TableSize.LARGE,
                        facilities=TableFacility.POWER_OUTLET | TableFacility.WHITEBOARD,
                    ),
                ],
            ),
            Room(
                name="Prospero's Dream",
                description="Side Room 2",
                facilities=RoomFacility.QUIET | RoomFacility.PRIVATE,
                tables=[
                    Table(name="42", size=TableSize.LARGE, facilities=TableFacility.POWER_OUTLET),
                ],
            ),
            Room(
                name="The Solar Basilica",
                description="Side Room 3",
                facilities=RoomFacility.QUIET,
                tables=[
                    Table(name="43", size=TableSize.LARGE, facilities=TableFacility.POWER_OUTLET),
                    Table(
                        name="44",
                        size=TableSize.SMALL,
                        facilities=TableFacility.POWER_OUTLET
                        | TableFacility.WHITEBOARD
                        | TableFacility.EXTRA_SIDETABLE,
                    ),
                ],
            ),
            Room(
                name="Night City",
                description="The Bar",
                facilities=RoomFacility.NONE,
            ),
            Room(
                name="The Vermission",
                description="Hallways and Corridors",
                facilities=RoomFacility.NONE,
            ),
        ],
        time_slots=[
            TimeSlot(
                name="Saturday Morning",
                start_time=dt.datetime(2026, 9, 12, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2026, 9, 12, 12, 0, tzinfo=NZT),
                checkin_open_time=dt.datetime(2026, 9, 11, 9, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Afternoon",
                start_time=dt.datetime(2026, 9, 12, 13, 30, tzinfo=NZT),
                end_time=dt.datetime(2026, 9, 12, 16, 30, tzinfo=NZT),
                checkin_open_time=dt.datetime(2026, 9, 11, 13, 30, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Evening",
                start_time=dt.datetime(2026, 9, 12, 18, 0, tzinfo=NZT),
                end_time=dt.datetime(2026, 9, 12, 22, 0, tzinfo=NZT),
                checkin_open_time=dt.datetime(2026, 9, 11, 18, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Morning",
                start_time=dt.datetime(2026, 9, 13, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2026, 9, 13, 12, 0, tzinfo=NZT),
                checkin_open_time=dt.datetime(2026, 9, 12, 9, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Afternoon",
                start_time=dt.datetime(2026, 9, 13, 14, 30, tzinfo=NZT),
                end_time=dt.datetime(2026, 9, 13, 18, 30, tzinfo=NZT),
                checkin_open_time=dt.datetime(2026, 9, 12, 14, 30, tzinfo=NZT),
            ),
        ],
    )


async def create_mock_event(session: AsyncSession) -> Event:
    """Create the mock event if it doesn't exist, or return the existing one."""
    result = await session.execute(select(Event).where(Event.name == EVENT_NAME))
    existing = result.scalar_one_or_none()

    if existing is not None:
        print(f'Event "{EVENT_NAME}" already exists (id={existing.id})')
        return existing

    event = build_event()
    session.add(event)
    await session.flush()

    room_count = len(event.rooms)
    table_count = sum(len(room.tables) for room in event.rooms)
    time_slot_count = len(event.time_slots)
    print(f'Created "{EVENT_NAME}" (id={event.id})')
    print(f"  {room_count} rooms, {table_count} tables, {time_slot_count} time slots")

    return event


async def main() -> None:
    engine = create_async_engine(SETTINGS.DATABASE_URL.render_as_string(hide_password=False))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session, session.begin():
        event = await create_mock_event(session)

    await engine.dispose()

    print()
    print("Suggested .env changes:")
    print(f"  DEFAULT_EVENT_ID={event.id}")
    print(f"  SITE_TITLE={EVENT_NAME}")


if __name__ == "__main__":
    asyncio.run(main())
