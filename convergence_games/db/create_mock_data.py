import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Event, Room, Table, TimeSlot


async def create_mock_data(db_session: AsyncSession) -> None:
    NZT = ZoneInfo("Pacific/Auckland")

    event = Event(
        name="Test Event",
        description="This is a test event",
        start_date=dt.datetime(2025, 9, 13, tzinfo=NZT),
        end_date=dt.datetime(2025, 9, 14, tzinfo=NZT),
        rooms=[
            Room(name="Room 1", description="This is room 1", tables=[Table(name="Table 1"), Table(name="Table 2")]),
            Room(name="Room 2", description="This is room 2", tables=[Table(name="Table 3"), Table(name="Table 4")]),
        ],
        time_slots=[
            TimeSlot(
                name="Saturday Morning",
                start_time=dt.datetime(2025, 9, 13, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 12, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Afternoon",
                start_time=dt.datetime(2025, 9, 13, 13, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 17, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Saturday Evening",
                start_time=dt.datetime(2025, 9, 13, 18, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 13, 22, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Morning",
                start_time=dt.datetime(2025, 9, 14, 9, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 14, 12, 0, tzinfo=NZT),
            ),
            TimeSlot(
                name="Sunday Afternoon",
                start_time=dt.datetime(2025, 9, 14, 13, 0, tzinfo=NZT),
                end_time=dt.datetime(2025, 9, 14, 17, 0, tzinfo=NZT),
            ),
        ],
    )

    async with db_session as session:
        session.add(event)
        await session.commit()
