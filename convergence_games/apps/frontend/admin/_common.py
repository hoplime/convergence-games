from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from convergence_games.db.models import Event, User
from convergence_games.lib.ocean import sink
from convergence_games.lib.permissions import user_has_permission

SqidInt = Annotated[int, BeforeValidator(sink)]


class PutEventManageScheduleSession(BaseModel):
    game: SqidInt
    table: SqidInt
    time_slot: SqidInt


def user_can_manage_submissions(user: User, event: Event) -> bool:
    return user_has_permission(user, "event", (event, event), "manage_submissions")
