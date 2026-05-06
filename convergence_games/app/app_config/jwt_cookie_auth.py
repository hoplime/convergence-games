import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, NoReturn, cast

from litestar.connection import ASGIConnection
from litestar.datastructures import Cookie
from litestar.exceptions import NotAuthorizedException
from litestar.middleware.authentication import AuthenticationResult
from litestar.security.jwt import JWTCookieAuth, JWTCookieAuthenticationMiddleware
from litestar.types import Receive, Scope, Send
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.context import user_id_ctx
from convergence_games.app.request_type import CustomToken
from convergence_games.db.enums import Role
from convergence_games.db.models import User, UserEventRole, UserSession
from convergence_games.settings import SETTINGS

ACCESS_COOKIE_KEY = "access"
REFRESH_COOKIE_KEY = "refresh"
LEGACY_COOKIE_KEY = "token"


def build_token_extras(user: User, event_roles: Sequence[UserEventRole]) -> dict[str, Any]:
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "over_18": user.over_18,
        "event_roles": [{"role": r.role.value, "event_id": r.event_id} for r in event_roles],
    }


def _user_from_token_claims(user_id: int, extras: dict[str, Any]) -> User:
    user = User(id=user_id, first_name=extras["first_name"], last_name=extras["last_name"], over_18=extras["over_18"])
    user.event_roles = [
        UserEventRole(role=Role(r["role"]), event_id=r["event_id"], user_id=user_id)
        for r in extras.get("event_roles", [])
    ]
    return user


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _decode_token(encoded: str) -> CustomToken:
    return CustomToken.decode(
        encoded_token=encoded,
        secret=SETTINGS.TOKEN_SECRET,
        algorithm="HS256",
    )


def _encode_access_token(user: User, event_roles: Sequence[UserEventRole]) -> tuple[str, dt.timedelta]:
    ttl = dt.timedelta(minutes=SETTINGS.ACCESS_TOKEN_TTL_MINUTES)
    extras = build_token_extras(user, event_roles)
    extras["token_type"] = "access"
    token = CustomToken(
        sub=str(user.id),
        exp=_now() + ttl,
        extras=extras,
        token_type="access",
    )
    return token.encode(secret=SETTINGS.TOKEN_SECRET, algorithm="HS256"), ttl


def _encode_refresh_token(user_id: int, jti: str) -> tuple[str, dt.timedelta]:
    ttl = dt.timedelta(days=SETTINGS.REFRESH_TOKEN_TTL_DAYS)
    token = CustomToken(
        sub=str(user_id),
        exp=_now() + ttl,
        jti=jti,
        extras={"token_type": "refresh"},
        token_type="refresh",
    )
    return token.encode(secret=SETTINGS.TOKEN_SECRET, algorithm="HS256"), ttl


def _make_access_cookie(value: str, ttl: dt.timedelta) -> Cookie:
    return Cookie(
        key=ACCESS_COOKIE_KEY,
        value=value,
        path="/",
        httponly=True,
        secure=SETTINGS.ENVIRONMENT == "production",
        samesite="lax",
        max_age=int(ttl.total_seconds()),
    )


def _make_refresh_cookie(value: str, ttl: dt.timedelta) -> Cookie:
    return Cookie(
        key=REFRESH_COOKIE_KEY,
        value=value,
        path="/",
        httponly=True,
        secure=SETTINGS.ENVIRONMENT == "production",
        samesite="lax",
        max_age=int(ttl.total_seconds()),
    )


def _make_clear_cookie(key: str) -> Cookie:
    return Cookie(
        key=key,
        value="",
        path="/",
        httponly=True,
        secure=SETTINGS.ENVIRONMENT == "production",
        samesite="lax",
        max_age=0,
    )


async def _issue_login_session(
    transaction: AsyncSession,
    user: User,
    event_roles: Sequence[UserEventRole],
    *,
    user_agent: str | None,
    family_id: str | None = None,
) -> tuple[Cookie, Cookie, str]:
    """Create a UserSession row and return (access_cookie, refresh_cookie, jti).

    family_id defaults to the new jti (i.e. a fresh session); pass an existing family_id when
    rotating a refresh token to keep the rotation chain together for reuse-detection.
    """
    jti = uuid.uuid4().hex
    family = family_id or jti
    now = _now()
    refresh_ttl = dt.timedelta(days=SETTINGS.REFRESH_TOKEN_TTL_DAYS)
    transaction.add(
        UserSession(
            user_id=user.id,
            jti=jti,
            family_id=family,
            expires_at=now + refresh_ttl,
            last_used_at=now,
            user_agent=user_agent,
        )
    )
    access_token, access_ttl = _encode_access_token(user, event_roles)
    refresh_token, _ = _encode_refresh_token(user.id, jti)
    return _make_access_cookie(access_token, access_ttl), _make_refresh_cookie(refresh_token, refresh_ttl), jti


async def _load_user_with_roles(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).options(selectinload(User.event_roles)).where(User.id == user_id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is not None:
        session.expunge_all()
    return user


async def _revoke_family(session: AsyncSession, family_id: str, reason: str) -> None:
    now = _now()
    await session.execute(
        update(UserSession)
        .where(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )


async def _revoke_session_by_jti(session: AsyncSession, jti: str, reason: str) -> None:
    now = _now()
    await session.execute(
        update(UserSession)
        .where(UserSession.jti == jti, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )


def _append_pending_cookie(scope: Scope, cookie: Cookie) -> None:
    state = scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
    pending = state.setdefault("pending_auth_cookies", [])
    pending.append(cookie)


def _set_current_session_jti(scope: Scope, jti: str | None) -> None:
    state = scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
    state["current_session_jti"] = jti


class TokenSessionAuthenticationMiddleware(JWTCookieAuthenticationMiddleware):
    """Authenticate via short-lived access cookie, falling back to refresh-cookie rotation
    or legacy single-token migration. Failures degrade to anonymous (no exception)."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Initialise the per-request state slot the middleware writes pending cookies into.
        state = scope.setdefault("state", {})  # pyright: ignore[reportArgumentType]
        state.setdefault("pending_auth_cookies", [])
        state.setdefault("current_session_jti", None)

        async def wrapped_send(message: Any) -> None:
            if message["type"] == "http.response.start":
                pending: list[Cookie] = state.get("pending_auth_cookies", [])
                if pending:
                    headers = list(message.get("headers", []) or [])
                    for cookie in pending:
                        headers.append(cookie.to_encoded_header())
                    message = {**message, "headers": headers}
            await send(message)

        await super().__call__(scope, receive, wrapped_send)

    async def authenticate_request(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthenticationResult:
        try:
            return await self._authenticate(connection)
        except NotAuthorizedException:
            return AuthenticationResult(user=None, auth=None)

    async def _authenticate(self, connection: ASGIConnection[Any, Any, Any, Any]) -> AuthenticationResult:
        cookies = connection.cookies
        access_cookie_value = cookies.get(ACCESS_COOKIE_KEY)
        refresh_cookie_value = cookies.get(REFRESH_COOKIE_KEY)
        legacy_cookie_value = cookies.get(LEGACY_COOKIE_KEY)

        # Hot path: valid access token.
        if access_cookie_value:
            try:
                token = _decode_token(access_cookie_value)
                if token.token_type == "access" and token.extras.get("first_name") is not None:
                    user_id = int(token.sub)
                    user_id_ctx.set(user_id)
                    user = _user_from_token_claims(user_id, token.extras)
                    return AuthenticationResult(user=user, auth=token)
            except NotAuthorizedException:
                # Access token is missing/expired/invalid; try refresh path.
                pass

        # Refresh path.
        if refresh_cookie_value:
            try:
                return await self._authenticate_via_refresh(connection, refresh_cookie_value)
            except NotAuthorizedException:
                # Refresh failed; fall through to legacy attempt and ultimately to anonymous.
                pass

        # Legacy migration path.
        if legacy_cookie_value:
            try:
                return await self._authenticate_via_legacy(connection, legacy_cookie_value)
            except NotAuthorizedException:
                _append_pending_cookie(connection.scope, _make_clear_cookie(LEGACY_COOKIE_KEY))

        return AuthenticationResult(user=None, auth=None)

    async def _authenticate_via_refresh(  # noqa: C901 - rotation/grace/reuse paths are intentionally branchy
        self, connection: ASGIConnection[Any, Any, Any, Any], encoded: str
    ) -> AuthenticationResult:
        def _mark_anonymous_and_raise() -> NoReturn:
            _append_pending_cookie(connection.scope, _make_clear_cookie(REFRESH_COOKIE_KEY))
            _append_pending_cookie(connection.scope, _make_clear_cookie(ACCESS_COOKIE_KEY))
            raise NotAuthorizedException()

        try:
            token = _decode_token(encoded)
        except NotAuthorizedException:
            _mark_anonymous_and_raise()

        if token.token_type != "refresh" or token.jti is None:
            _mark_anonymous_and_raise()

        engine = cast(AsyncEngine, connection.app.state.db_engine)
        async with AsyncSession(engine) as session:
            # Phase 1: load the row + commit any rejection-side-effect writes (revoke).
            # Read every attribute we'll need later *inside* this block — once it commits, the
            # ORM expires attributes and accessing them later triggers a refresh that needs a
            # live transaction.
            rejected = ""
            family_id = ""
            sibling_jti: str | None = None
            sibling_user_id: int | None = None
            row_user_id: int | None = None
            async with session.begin():
                row = (
                    await session.execute(select(UserSession).where(UserSession.jti == token.jti))
                ).scalar_one_or_none()
                if row is None:
                    rejected = "no_row"
                else:
                    now = _now()
                    family_id = row.family_id
                    row_user_id = row.user_id
                    if row.expires_at < now:
                        await _revoke_session_by_jti(session, row.jti, reason="expired")
                        rejected = "expired"
                    elif row.revoked_at is not None:
                        grace = dt.timedelta(seconds=SETTINGS.REFRESH_ROTATION_GRACE_SECONDS)
                        if row.revoked_reason == "rotated" and now < row.revoked_at + grace:
                            sibling = (
                                await session.execute(
                                    select(UserSession).where(
                                        UserSession.family_id == row.family_id,
                                        UserSession.revoked_at.is_(None),
                                    )
                                )
                            ).scalar_one_or_none()
                            if sibling is None:
                                rejected = "no_sibling"
                            else:
                                sibling_jti = sibling.jti
                                sibling_user_id = sibling.user_id
                                sibling.last_used_at = now
                        else:
                            await _revoke_family(session, row.family_id, reason="reuse_detected")
                            rejected = "reuse_detected"

            if rejected:
                _mark_anonymous_and_raise()

            # Phase 2: load user + (if rotation) mint new session row, in a new transaction.
            async with session.begin():
                if sibling_jti is not None and sibling_user_id is not None:
                    # Grace-window branch: reuse the sibling row; just mint a fresh access token.
                    user = await _load_user_with_roles(session, sibling_user_id)
                    if user is None:
                        _mark_anonymous_and_raise()
                    access_token, access_ttl = _encode_access_token(user, list(user.event_roles))
                    _append_pending_cookie(connection.scope, _make_access_cookie(access_token, access_ttl))
                    _set_current_session_jti(connection.scope, sibling_jti)
                    user_id_ctx.set(user.id)
                    return AuthenticationResult(user=user, auth=token)

                # Standard rotation branch.
                assert row_user_id is not None
                assert token.jti is not None
                await _revoke_session_by_jti(session, token.jti, reason="rotated")
                user = await _load_user_with_roles(session, row_user_id)
                if user is None:
                    _mark_anonymous_and_raise()

                access_cookie, refresh_cookie, new_jti = await _issue_login_session(
                    session,
                    user,
                    list(user.event_roles),
                    user_agent=connection.headers.get("user-agent"),
                    family_id=family_id,
                )
                _append_pending_cookie(connection.scope, access_cookie)
                _append_pending_cookie(connection.scope, refresh_cookie)
                _set_current_session_jti(connection.scope, new_jti)
                user_id_ctx.set(user.id)
                return AuthenticationResult(user=user, auth=token)

    async def _authenticate_via_legacy(
        self, connection: ASGIConnection[Any, Any, Any, Any], encoded: str
    ) -> AuthenticationResult:
        token = _decode_token(encoded)  # raises NotAuthorizedException if invalid
        # If the cookie is actually one of the new tokens (e.g. someone smuggled an access
        # token under the old name), refuse to migrate — treat as anonymous.
        if token.token_type in ("access", "refresh"):
            raise NotAuthorizedException()
        try:
            user_id = int(token.sub)
        except ValueError as e:
            raise NotAuthorizedException() from e
        user_id_ctx.set(user_id)

        engine = cast(AsyncEngine, connection.app.state.db_engine)
        async with AsyncSession(engine) as session:
            async with session.begin():
                user = await _load_user_with_roles(session, user_id)
                if user is None:
                    raise NotAuthorizedException()
                access_cookie, refresh_cookie, new_jti = await _issue_login_session(
                    session,
                    user,
                    list(user.event_roles),
                    user_agent=connection.headers.get("user-agent"),
                )
        _append_pending_cookie(connection.scope, access_cookie)
        _append_pending_cookie(connection.scope, refresh_cookie)
        _append_pending_cookie(connection.scope, _make_clear_cookie(LEGACY_COOKIE_KEY))
        _set_current_session_jti(connection.scope, new_jti)
        return AuthenticationResult(user=user, auth=token)


# `retrieve_user_handler` is required by Litestar's JWTCookieAuth wiring even though our
# middleware override no longer calls into it. Kept as a defensive fallback that mirrors
# the legacy claim-reconstruction behaviour.
async def retrieve_user_handler(token: CustomToken, connection: ASGIConnection[Any, Any, Any, Any]) -> User | None:
    user_id = int(token.sub)
    user_id_ctx.set(user_id)

    if token.extras.get("first_name") is not None:
        return _user_from_token_claims(user_id, token.extras)

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as async_session:
        async with async_session.begin():
            stmt = select(User).options(selectinload(User.event_roles)).where(User.id == user_id)
            user = (await async_session.execute(stmt)).scalar_one_or_none()
            async_session.expunge_all()

    return user


jwt_cookie_auth = JWTCookieAuth(
    token_secret=SETTINGS.TOKEN_SECRET,
    retrieve_user_handler=retrieve_user_handler,
    token_cls=CustomToken,
    authentication_middleware_class=TokenSessionAuthenticationMiddleware,
    exclude=["/site.webmanifest", "/static"],
    default_token_expiration=dt.timedelta(minutes=SETTINGS.ACCESS_TOKEN_TTL_MINUTES),
    key=ACCESS_COOKIE_KEY,
)
