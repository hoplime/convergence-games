from typing import Annotated

from pydantic import BeforeValidator

from convergence_games.db.models import Event, User
from convergence_games.lib.ocean import sink
from convergence_games.lib.permissions import user_has_permission

SqidInt = Annotated[int, BeforeValidator(sink)]


def user_can_manage_submissions(user: User, event: Event) -> bool:
    return user_has_permission(user, "event", (event, event), "manage_submissions")
