from typing import Annotated

from litestar import Controller, Response, put
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import Event, Game, User, UserGamePlayed, UserGamePreference
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.permissions import user_has_permission


class RatingPutData(BaseModel):
    rating: UserGamePreferenceValue


class AllowPlayAgainPutData(BaseModel):
    allow_play_again: bool = False


class PreferencesController(Controller):
    path = "/game"

    @put(path="/{game_sqid:str}/preference")
    async def put_game_preference(
        self,
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

    @put(path="/{game_sqid:str}/already-played")
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
