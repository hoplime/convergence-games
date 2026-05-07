from litestar.di import Provide
from litestar.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.exceptions import SlugRedirectError
from convergence_games.app.request_type import Request
from convergence_games.db.models import Event
from convergence_games.db.ocean import Sqid, sink
from convergence_games.settings import SETTINGS


def looks_like_sqid(value: str) -> bool:
    """Heuristic: slugs are lowercase[-]; sqids in this app's default alphabet contain uppercase.

    Lowercase-only values without hyphens are ambiguous — return True so the caller will
    try a sqid decode after the slug lookup misses. The decode is cheap and wraps `IndexError`
    when sqids returns an empty list for an invalid string.
    """
    if not value:
        return False
    if "-" in value:
        return False
    return any(c.isupper() for c in value) or value.isalnum()


def _decode_sqid_safely(value: str) -> int | None:
    try:
        return sink(Sqid(value))
    except (IndexError, ValueError):
        return None


def event_with(*options: ExecutableOption) -> Provide:
    """Dependency factory that loads an Event by slug-or-sqid path key.

    Accepts the path parameter `event_key`, trying slug match first. If no slug
    match and the value looks like a sqid, attempts a sqid lookup; on success
    raises `SlugRedirectError` so the request 301-redirects to the canonical slug URL.
    Falls back to the default event when `event_key` is None.
    """

    async def wrapper(
        request: Request,
        transaction: AsyncSession,
        event_key: str | None = None,
    ) -> Event:
        if event_key is None:
            stmt = select(Event).options(*options).where(Event.id == SETTINGS.DEFAULT_EVENT_ID)
            event = (await transaction.execute(stmt)).scalar_one_or_none()
            if event is None:
                raise HTTPException(status_code=404, detail="Event not found")
            return event

        # Try slug first (cheap unique-indexed lookup).
        stmt = select(Event).options(*options).where(Event.slug == event_key)
        event = (await transaction.execute(stmt)).scalar_one_or_none()
        if event is not None:
            return event

        # Fall back to sqid decode for legacy URLs; on hit, redirect to canonical slug URL.
        if looks_like_sqid(event_key):
            event_id = _decode_sqid_safely(event_key)
            if event_id is not None:
                stmt = select(Event).options(*options).where(Event.id == event_id)
                event = (await transaction.execute(stmt)).scalar_one_or_none()
                if event is not None:
                    raise SlugRedirectError(_canonical_path(request, event_key, event.slug))

        raise HTTPException(status_code=404, detail="Event not found")

    return Provide(wrapper)


def _canonical_path(request: Request, old_key: str, new_key: str) -> str:
    """Replace the matched path key in the request URL with the canonical slug.

    Uses path/query string substitution rather than `route_reverse` so we don't
    have to pin handler names across many controllers.
    """
    path = request.scope["path"]
    canonical = path.replace(f"/{old_key}/", f"/{new_key}/", 1)
    if canonical == path and path.endswith(f"/{old_key}"):
        canonical = path[: -len(old_key)] + new_key
    query = request.scope.get("query_string", b"")
    if query:
        canonical = f"{canonical}?{query.decode()}"
    return canonical
