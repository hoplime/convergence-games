"""Application-specific JWT multi-cookie auth wiring.

Instantiates JWTMultiCookieAuth with app-specific handlers for refresh-token
rotation, legacy-token migration, and user retrieval. All generic multi-cookie
logic lives in convergence_games.app.common.jwt_multi_cookie.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, cast

from litestar.connection import ASGIConnection
from litestar.security.jwt import Token
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.common.jwt_multi_cookie import JWTMultiCookieAuth, RefreshResult
from convergence_games.app.context import user_id_ctx
from convergence_games.app.request_type import CustomToken
from convergence_games.db.enums import Role
from convergence_games.db.models import User, UserEventRole, UserSession
from convergence_games.settings import SETTINGS


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


# --- token claim helpers ---


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


# --- DB helpers ---


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


async def create_user_session(
    transaction: AsyncSession,
    user_id: int,
    jti: str,
    *,
    user_agent: str | None,
    family_id: str | None = None,
) -> str:
    """Create a UserSession row. Returns the jti."""
    family = family_id or jti
    now = _now()
    refresh_ttl = dt.timedelta(days=SETTINGS.REFRESH_TOKEN_TTL_DAYS)
    transaction.add(
        UserSession(
            user_id=user_id,
            jti=jti,
            family_id=family,
            expires_at=now + refresh_ttl,
            last_used_at=now,
            user_agent=user_agent,
        )
    )
    return jti


# --- Litestar retrieve_user_handler ---


async def retrieve_user_handler(token: CustomToken, connection: ASGIConnection[Any, Any, Any, Any]) -> User | None:
    """Reconstruct a User from the access token's claims (hot path, no DB).

    Falls back to a DB lookup for tokens without claim extras.
    """
    user_id = int(token.sub)
    user_id_ctx.set(user_id)

    if token.extras.get("first_name") is not None:
        return _user_from_token_claims(user_id, token.extras)

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as async_session:
        async with async_session.begin():
            user = await _load_user_with_roles(async_session, user_id)
    return user


# --- refresh / legacy handlers ---


async def _handle_refresh(  # noqa: C901
    token: Token,
    connection: ASGIConnection[Any, Any, Any, Any],
) -> RefreshResult | None:
    """Validate and rotate a refresh token. Returns RefreshResult or None on failure."""
    token_type = getattr(token, "token_type", None) or token.extras.get("token_type")
    if token_type != "refresh" or token.jti is None:
        return None

    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as session:
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
            return None

        async with session.begin():
            if sibling_jti is not None and sibling_user_id is not None:
                user = await _load_user_with_roles(session, sibling_user_id)
                if user is None:
                    return None
                user_id_ctx.set(user.id)
                return RefreshResult(
                    user=user,
                    token_extras=build_token_extras(user, list(user.event_roles)),
                    session_jti=sibling_jti,
                )

            assert row_user_id is not None
            assert token.jti is not None
            await _revoke_session_by_jti(session, token.jti, reason="rotated")
            user = await _load_user_with_roles(session, row_user_id)
            if user is None:
                return None

            new_jti = uuid.uuid4().hex
            await create_user_session(
                session,
                user.id,
                new_jti,
                user_agent=connection.headers.get("user-agent"),
                family_id=family_id,
            )
            user_id_ctx.set(user.id)
            return RefreshResult(
                user=user,
                token_extras=build_token_extras(user, list(user.event_roles)),
                cookies=[jwt_cookie_auth.create_refresh_cookie(str(user.id), new_jti)],
                session_jti=new_jti,
            )


async def _handle_legacy(
    token: Token,
    connection: ASGIConnection[Any, Any, Any, Any],
) -> RefreshResult | None:
    """Migrate a legacy single-cookie token to the new access + refresh pair."""
    token_type = getattr(token, "token_type", None) or token.extras.get("token_type")
    if token_type in ("access", "refresh"):
        return None

    try:
        user_id = int(token.sub)
    except ValueError:
        return None

    user_id_ctx.set(user_id)
    engine = cast(AsyncEngine, connection.app.state.db_engine)
    async with AsyncSession(engine) as session:
        async with session.begin():
            user = await _load_user_with_roles(session, user_id)
            if user is None:
                return None
            new_jti = uuid.uuid4().hex
            await create_user_session(
                session,
                user.id,
                new_jti,
                user_agent=connection.headers.get("user-agent"),
            )

    return RefreshResult(
        user=user,
        token_extras=build_token_extras(user, list(user.event_roles)),
        cookies=[jwt_cookie_auth.create_refresh_cookie(str(user.id), new_jti)],
        session_jti=new_jti,
    )


# --- auth instance ---

jwt_cookie_auth = JWTMultiCookieAuth(
    token_secret=SETTINGS.TOKEN_SECRET,
    retrieve_user_handler=retrieve_user_handler,
    token_cls=CustomToken,
    key="access",
    secure=SETTINGS.ENVIRONMENT == "production",
    default_token_expiration=dt.timedelta(minutes=SETTINGS.ACCESS_TOKEN_TTL_MINUTES),
    refresh_key="refresh",
    legacy_key="token",
    refresh_token_expiration=dt.timedelta(days=SETTINGS.REFRESH_TOKEN_TTL_DAYS),
    rotation_grace_seconds=SETTINGS.REFRESH_ROTATION_GRACE_SECONDS,
    refresh_handler=_handle_refresh,
    legacy_handler=_handle_legacy,
    exclude=["/site.webmanifest", "/static"],
)
