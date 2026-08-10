from collections.abc import AsyncGenerator

from litestar.di import Provide
from litestar.exceptions import ClientException, HTTPException, NotFoundException
from litestar.status_codes import HTTP_409_CONFLICT
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.db.models import Event, Game, Party, TimeSlot, User
from convergence_games.lib.exceptions import UserNotLoggedInError
from convergence_games.lib.ocean import Sqid, sink, sink_upper
from convergence_games.lib.request_type import Request
from convergence_games.services import ImageLoader, image_loader_from_settings
from convergence_games.settings import SETTINGS

# region Global dependency providers


async def provide_transaction(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    try:
        async with db_session.begin():
            yield db_session
    except IntegrityError as exc:
        raise ClientException(
            status_code=HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


async def provide_user(request: Request) -> User:
    if request.user is None:
        raise UserNotLoggedInError("User must be logged in to perform this action.")
    return request.user


async def provide_image_loader() -> ImageLoader:
    return image_loader_from_settings


dependencies = {
    "transaction": Provide(provide_transaction),
    "user": Provide(provide_user),
    "image_loader": Provide(provide_image_loader),
}


# region Entity dependency factories


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


def game_with(*options: ExecutableOption) -> Provide:
    """Dependency factory that loads a Game by sqid."""

    async def wrapper(
        transaction: AsyncSession,
        game_sqid: Sqid,
    ) -> Game:
        game_id = sink(game_sqid)
        game = (await transaction.execute(select(Game).options(*options).where(Game.id == game_id))).scalar_one_or_none()

        if not game:
            raise NotFoundException(detail="Game not found")

        return game

    return Provide(wrapper)


def party_with(*options: ExecutableOption, raise_404: bool = False) -> Provide:
    """Dependency factory that loads a Party by invite sqid (uppercase)."""

    async def wrapper(
        transaction: AsyncSession,
        invite_sqid: Sqid,
    ) -> Party | None:
        try:
            party_id = sink_upper(invite_sqid)
            party = (
                await transaction.execute(select(Party).options(*options).where(Party.id == party_id))
            ).scalar_one_or_none()
        except Exception:
            party = None

        if not party and raise_404:
            raise HTTPException(status_code=404, detail="Party not found.")

        return party

    return Provide(wrapper)


def time_slot_with(*options: ExecutableOption, raise_404: bool = False) -> Provide:
    """Dependency factory that loads a TimeSlot by sqid."""

    async def wrapper(
        transaction: AsyncSession,
        time_slot_sqid: Sqid,
    ) -> TimeSlot | None:
        time_slot_id: int = sink(time_slot_sqid)
        time_slot = (
            await transaction.execute(select(TimeSlot).options(*options).where(TimeSlot.id == time_slot_id))
        ).scalar_one_or_none()

        if not time_slot and raise_404:
            raise HTTPException(status_code=404, detail="Time slot not found.")

        return time_slot

    return Provide(wrapper)
