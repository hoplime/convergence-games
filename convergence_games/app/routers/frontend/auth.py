"""Auth-related endpoints: per-session revocation and 'sign out everywhere'."""

import datetime as dt
from typing import Annotated

from litestar import Controller, post
from litestar.exceptions import HTTPException
from litestar.params import Parameter
from litestar.plugins.htmx import ClientRedirect
from litestar.response import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.app_config.jwt_cookie_auth import (
    ACCESS_COOKIE_KEY,
    LEGACY_COOKIE_KEY,
    REFRESH_COOKIE_KEY,
    _make_clear_cookie,
)
from convergence_games.app.common.auth import revoke_all_sessions_for_user
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.db.models import UserSession
from convergence_games.db.ocean import Sqid, sink


class AuthController(Controller):
    path = "/auth"

    @post(path="/sessions/{session_sqid:str}/revoke", guards=[user_guard])
    async def post_revoke_session(
        self,
        session_sqid: Annotated[str, Parameter()],
        request: Request,
        transaction: AsyncSession,
    ) -> Response[None]:
        assert request.user is not None
        try:
            session_id = sink(Sqid(session_sqid))
        except Exception as e:
            raise HTTPException(detail="Session not found", status_code=404) from e

        row = (
            await transaction.execute(select(UserSession).where(UserSession.id == session_id))
        ).scalar_one_or_none()
        if row is None or row.user_id != request.user.id:
            # 404 (not 403) so a logged-in user can't probe for the existence of other users' sessions.
            raise HTTPException(detail="Session not found", status_code=404)
        if row.revoked_at is None:
            row.revoked_at = dt.datetime.now(tz=dt.timezone.utc)
            row.revoked_reason = "admin"

        # If the user revoked their own current session, clear cookies on the response so they
        # become anonymous on next request.
        clear_self = request.scope["state"].get("current_session_jti") == row.jti
        response: Response[None] = Response(content=None, status_code=204)
        if clear_self:
            response.cookies.append(_make_clear_cookie(ACCESS_COOKIE_KEY))
            response.cookies.append(_make_clear_cookie(REFRESH_COOKIE_KEY))
            response.cookies.append(_make_clear_cookie(LEGACY_COOKIE_KEY))
            # Tell HTMX to follow up by reloading.
            response.headers["HX-Refresh"] = "true"
        else:
            # Tell HTMX to refresh the sessions panel.
            response.headers["HX-Trigger"] = "sessions-changed"
        return response

    @post(path="/logout-everywhere", guards=[user_guard])
    async def post_logout_everywhere(
        self,
        request: Request,
        transaction: AsyncSession,
    ) -> ClientRedirect:
        assert request.user is not None
        await revoke_all_sessions_for_user(transaction, request.user.id, reason="logout_everywhere")
        response = ClientRedirect("/sign-in")
        response.cookies.append(_make_clear_cookie(ACCESS_COOKIE_KEY))
        response.cookies.append(_make_clear_cookie(REFRESH_COOKIE_KEY))
        response.cookies.append(_make_clear_cookie(LEGACY_COOKIE_KEY))
        return response
