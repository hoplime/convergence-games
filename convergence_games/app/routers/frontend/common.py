from litestar.di import Provide
from litestar.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.db.models import Event
from convergence_games.db.ocean import Sqid, sink
from convergence_games.settings import SETTINGS


def event_with(*options: ExecutableOption) -> Provide:
    """Dependency factory that loads an Event by sqid, falling back to the default event."""

    async def wrapper(
        transaction: AsyncSession,
        event_sqid: Sqid | None = None,
    ) -> Event:
        event_id: int = sink(event_sqid) if event_sqid is not None else SETTINGS.DEFAULT_EVENT_ID
        stmt = select(Event).options(*options).where(Event.id == event_id)
        event = (await transaction.execute(stmt)).scalar_one_or_none()
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return Provide(wrapper)
