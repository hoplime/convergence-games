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

from convergence_games.app.app_config.jwt_cookie_auth import jwt_cookie_auth
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
            raise HTTPException(detail="Session not found", status_code=404)
        if row.revoked_at is None:
            row.revoked_at = dt.datetime.now(tz=dt.timezone.utc)
            row.revoked_reason = "admin"

        clear_self = request.state.get("current_session_jti") == row.jti
        response: Response[None] = Response(content=None, status_code=204)
        if clear_self:
            jwt_cookie_auth.delete_cookies_from_response(response)
            response.headers["HX-Refresh"] = "true"
        else:
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
        jwt_cookie_auth.delete_cookies_from_response(response)
        return response
