import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Event, Room, Table


async def create_mock_data(db_session: AsyncSession) -> None:
    event = Event(
        name="Test Event",
        description="This is a test event",
        start_date=dt.datetime(2025, 7, 14, tzinfo=dt.timezone.utc),
        end_date=dt.datetime(2025, 7, 16, tzinfo=dt.timezone.utc),
        rooms=[
            Room(name="Room 1", description="This is room 1", tables=[Table(name="Table 1"), Table(name="Table 2")]),
            Room(name="Room 2", description="This is room 2", tables=[Table(name="Table 3"), Table(name="Table 4")]),
        ],
    )

    async with db_session as session:
        session.add(event)
        await session.commit()
