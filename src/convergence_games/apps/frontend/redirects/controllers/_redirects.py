from litestar import Controller, get
from litestar.response import Redirect

from convergence_games.settings import SETTINGS


class RedirectsController(Controller):
    """Redirect shortcut URLs to their event-scoped equivalents using the default event."""

    @get("/games")
    async def redirect_games(self) -> Redirect:
        return Redirect(path=f"/event/{SETTINGS.DEFAULT_EVENT_SQID}/games")

    @get("/planner")
    async def redirect_planner(self) -> Redirect:
        return Redirect(path=f"/event/{SETTINGS.DEFAULT_EVENT_SQID}/planner")

    @get("/submit-game")
    async def redirect_submit_game(self) -> Redirect:
        return Redirect(path=f"/event/{SETTINGS.DEFAULT_EVENT_SQID}/submit-game")
