from typing import Annotated

from litestar import Controller, Response, put
from litestar.di import Provide
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel

from convergence_games.db.enums import UserGamePreferenceValue
from convergence_games.db.models import User
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.permissions import user_has_permission

from ..services import PreferenceService, provide_preference_service


class RatingPutData(BaseModel):
    rating: UserGamePreferenceValue


class AllowPlayAgainPutData(BaseModel):
    allow_play_again: bool = False


class PreferencesController(Controller):
    path = "/game"
    dependencies = {"preference_service": Provide(provide_preference_service)}

    @put(path="/{game_sqid:str}/preference")
    async def put_game_preference(
        self,
        game_sqid: Sqid,
        user: User,
        preference_service: PreferenceService,
        data: Annotated[RatingPutData, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        game_id: int = sink(game_sqid)

        event = await preference_service.get_event_for_game(game_id)
        if event is not None and not event.is_preferences_open():
            if not user_has_permission(user, "event", (event, event), "manage_submissions"):
                raise AlertError([Alert("alert-warning", "Preferences are not currently open for this event.")])

        await preference_service.set_game_preference(user_id=user.id, game_id=game_id, rating=data.rating)
        return Response(content="", status_code=204)

    @put(path="/{game_sqid:str}/already-played")
    async def put_game_already_played(
        self,
        game_sqid: Sqid,
        user: User,
        preference_service: PreferenceService,
        data: Annotated[AllowPlayAgainPutData, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        game_id: int = sink(game_sqid)
        await preference_service.set_game_already_played(
            user_id=user.id, game_id=game_id, allow_play_again=data.allow_play_again
        )
        return Response(content="", status_code=204)
