from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import Event, Game, UserGamePlayed, UserGamePreference


class PreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event_for_game(self, game_id: int) -> Event | None:
        return (
            await self._session.execute(select(Event).join(Game, Game.event_id == Event.id).where(Game.id == game_id))
        ).scalar_one_or_none()

    async def set_game_preference(
        self, *, user_id: int, game_id: int, rating: UserGamePreferenceValue
    ) -> UserGamePreference:
        user_game_preference = (
            await self._session.execute(
                select(UserGamePreference).where(
                    UserGamePreference.game_id == game_id,
                    UserGamePreference.user_id == user_id,
                    UserGamePreference.frozen_at_time_slot_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if user_game_preference is None:
            user_game_preference = UserGamePreference(game_id=game_id, user_id=user_id)
        user_game_preference.preference = rating
        self._session.add(user_game_preference)
        return user_game_preference

    async def set_game_already_played(self, *, user_id: int, game_id: int, allow_play_again: bool) -> UserGamePlayed:
        user_game_played = (
            await self._session.execute(
                select(UserGamePlayed).where(
                    UserGamePlayed.game_id == game_id,
                    UserGamePlayed.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if user_game_played is None:
            user_game_played = UserGamePlayed(game_id=game_id, user_id=user_id)
        user_game_played.allow_play_again = allow_play_again
        self._session.add(user_game_played)
        return user_game_played


async def provide_preference_service(transaction: AsyncSession) -> PreferenceService:
    return PreferenceService(transaction)
