from typing import Annotated

from litestar import Controller, Response, get, put
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.alerts import Alert, AlertError
from convergence_games.app.exceptions import SlugRedirectError
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.app.routers.frontend.common import looks_like_sqid
from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import (
    Event,
    Game,
    Session,
    Table,
    User,
    UserEventD20Transaction,
    UserGamePlayed,
    UserGamePreference,
)
from convergence_games.db.ocean import Sqid, sink
from convergence_games.permissions import user_has_permission
from convergence_games.services import ImageLoader


class RatingPutData(BaseModel):
    rating: UserGamePreferenceValue


class AllowPlayAgainPutData(BaseModel):
    allow_play_again: bool = False


def _decode_sqid_safely(value: str) -> int | None:
    try:
        return sink(Sqid(value))
    except (IndexError, ValueError):
        return None


def _game_load_options() -> tuple[ExecutableOption, ...]:
    return (
        selectinload(Game.system),
        selectinload(Game.gamemaster),
        selectinload(Game.event),
        selectinload(Game.game_requirement),
        selectinload(Game.genres),
        selectinload(Game.content_warnings),
        selectinload(Game.images),
    )


async def _resolve_event_for_game(transaction: AsyncSession, event_key: str) -> tuple[Event, bool]:
    """Resolve an Event by slug-or-sqid. Returns (event, matched_via_sqid)."""
    event = (await transaction.execute(select(Event).where(Event.slug == event_key))).scalar_one_or_none()
    if event is not None:
        return event, False
    if looks_like_sqid(event_key):
        event_id = _decode_sqid_safely(event_key)
        if event_id is not None:
            event = (await transaction.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
            if event is not None:
                return event, True
    raise HTTPException(status_code=404, detail="Event not found")


async def _resolve_game_for_event(transaction: AsyncSession, event: Event, game_key: str) -> tuple[Game, bool]:
    """Resolve a Game by slug-or-sqid scoped to the given Event. Returns (game, matched_via_sqid)."""
    stmt = select(Game).options(*_game_load_options()).where(Game.event_id == event.id)
    game = (await transaction.execute(stmt.where(Game.slug == game_key))).scalar_one_or_none()
    if game is not None:
        return game, False
    if looks_like_sqid(game_key):
        game_id = _decode_sqid_safely(game_key)
        if game_id is not None:
            game = (await transaction.execute(stmt.where(Game.id == game_id))).scalar_one_or_none()
            if game is not None:
                return game, True
    raise HTTPException(status_code=404, detail="Game not found")


async def _render_game_page(
    request: Request,
    transaction: AsyncSession,
    image_loader: ImageLoader,
    game: Game,
) -> Template:
    if request.user:
        user_game_preference = (
            await transaction.execute(
                select(UserGamePreference).where(
                    UserGamePreference.game_id == game.id,
                    UserGamePreference.user_id == request.user.id,
                    UserGamePreference.frozen_at_time_slot_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        preference = user_game_preference.preference if user_game_preference else None
        latest_d20_transaction = (
            await transaction.execute(
                select(UserEventD20Transaction)
                .where(UserEventD20Transaction.user_id == request.user.id)
                .where(UserEventD20Transaction.event_id == game.event_id)
                .order_by(UserEventD20Transaction.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        user_game_played = (
            await transaction.execute(
                select(UserGamePlayed).where(
                    UserGamePlayed.user_id == request.user.id, UserGamePlayed.game_id == game.id
                )
            )
        ).scalar_one_or_none()
    else:
        preference = None
        latest_d20_transaction = None
        user_game_played = None

    game_image_urls = [
        {
            "full": await image_loader.get_image_path(image.lookup_key),
            "thumbnail": await image_loader.get_image_path(image.lookup_key, size=300),
        }
        for image in game.images
    ]

    scheduled_sessions = (
        (
            await transaction.execute(
                select(Session)
                .where(
                    Session.game_id == game.id,
                    Session.committed,
                )
                .options(
                    selectinload(Session.table).selectinload(Table.room),
                    selectinload(Session.time_slot),
                )
            )
        )
        .scalars()
        .all()
    )

    return HTMXBlockTemplate(
        template_name="pages/game.html.jinja",
        block_name=request.htmx.target,
        context={
            "game": game,
            "game_image_urls": game_image_urls,
            "preference": preference,
            "user_game_played": user_game_played,
            "scheduled_sessions": sorted(scheduled_sessions, key=lambda s: s.time_slot.start_time),
            "has_d20": latest_d20_transaction is not None and latest_d20_transaction.current_balance > 0,
        },
    )


class GameController(Controller):
    @get(path="/event/{event_key:str}/game/{game_key:str}")
    async def get_game_by_event_and_slug(
        self,
        request: Request,
        event_key: str,
        game_key: str,
        transaction: AsyncSession,
        image_loader: ImageLoader,
    ) -> Template:
        event, event_via_sqid = await _resolve_event_for_game(transaction, event_key)
        game, game_via_sqid = await _resolve_game_for_event(transaction, event, game_key)
        if event_via_sqid or game_via_sqid:
            raise SlugRedirectError(f"/event/{event.slug}/game/{game.slug}")
        return await _render_game_page(request, transaction, image_loader, game)

    @get(path="/game/{game_sqid:str}")
    async def get_game_legacy(
        self,
        game_sqid: Sqid,
        transaction: AsyncSession,
    ) -> Response[str]:
        """Decode the sqid, look up the game, and 301 to the canonical slug URL."""
        game_id = _decode_sqid_safely(game_sqid)
        if game_id is None:
            raise HTTPException(status_code=404, detail="Game not found")
        game = (
            await transaction.execute(select(Game).options(selectinload(Game.event)).where(Game.id == game_id))
        ).scalar_one_or_none()
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        raise SlugRedirectError(f"/event/{game.event.slug}/game/{game.slug}")

    @put(path="/game/{game_sqid:str}/preference")
    async def put_game_preference(
        self,
        request: Request,
        game_sqid: Sqid,
        user: User,
        transaction: AsyncSession,
        data: Annotated[RatingPutData, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        game_id: int = sink(game_sqid)

        event = (
            await transaction.execute(select(Event).join(Game, Game.event_id == Event.id).where(Game.id == game_id))
        ).scalar_one_or_none()
        if event is not None and not event.is_preferences_open():
            if not user_has_permission(user, "event", (event, event), "manage_submissions"):
                raise AlertError([Alert("alert-warning", "Preferences are not currently open for this event.")])

        user_game_preference = (
            await transaction.execute(
                select(UserGamePreference).where(
                    UserGamePreference.game_id == game_id,
                    UserGamePreference.user_id == user.id,
                    UserGamePreference.frozen_at_time_slot_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if user_game_preference is None:
            user_game_preference = UserGamePreference(game_id=game_id, user_id=user.id)
        user_game_preference.preference = data.rating
        transaction.add(user_game_preference)
        return Response(content="", status_code=204)

    @put(path="/game/{game_sqid:str}/already-played")
    async def put_game_already_played(
        self,
        game_sqid: Sqid,
        user: User,
        transaction: AsyncSession,
        data: Annotated[AllowPlayAgainPutData, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        game_id: int = sink(game_sqid)
        user_game_played = (
            await transaction.execute(
                select(UserGamePlayed).where(
                    UserGamePlayed.game_id == game_id,
                    UserGamePlayed.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if user_game_played is None:
            user_game_played = UserGamePlayed(game_id=game_id, user_id=user.id)
        user_game_played.allow_play_again = data.allow_play_again
        transaction.add(user_game_played)
        return Response(content="", status_code=204)
