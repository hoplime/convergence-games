from litestar import Controller, get
from litestar.response import Redirect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Event
from convergence_games.settings import SETTINGS

# Cached process-locally so /games, /planner, /submit-game don't hit the DB every request.
_default_event_key_cache: str | None = None


async def _default_event_key(transaction: AsyncSession) -> str:
    global _default_event_key_cache
    if _default_event_key_cache is None:
        slug = (
            await transaction.execute(select(Event.slug).where(Event.id == SETTINGS.DEFAULT_EVENT_ID))
        ).scalar_one_or_none()
        # Fall back to the sqid form if the default event row isn't present (rare in dev/test).
        # `event_with` will then 301 to the canonical slug once the event exists.
        _default_event_key_cache = slug or SETTINGS.DEFAULT_EVENT_SQID
    return _default_event_key_cache


class RedirectsController(Controller):
    """Redirect shortcut URLs to their event-scoped equivalents using the default event."""

    @get("/games")
    async def redirect_games(self, transaction: AsyncSession) -> Redirect:
        return Redirect(path=f"/event/{await _default_event_key(transaction)}/games")

    @get("/planner")
    async def redirect_planner(self, transaction: AsyncSession) -> Redirect:
        return Redirect(path=f"/event/{await _default_event_key(transaction)}/planner")

    @get("/submit-game")
    async def redirect_submit_game(self, transaction: AsyncSession) -> Redirect:
        return Redirect(path=f"/event/{await _default_event_key(transaction)}/submit-game")
