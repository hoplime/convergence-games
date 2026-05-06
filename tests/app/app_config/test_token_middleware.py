"""Tests for the access/refresh token middleware helpers and rotation logic.

We exercise the middleware indirectly: the helpers (`_issue_login_session`,
`_revoke_session_by_jti`, `_revoke_family`, `_decode_token`) and the rotation/migration
paths via a thin fake ASGI connection that captures pending cookies. Building a full
Litestar test app would force a real Postgres dependency; the helper-level tests give us
the same coverage at much lower setup cost.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from litestar.exceptions import NotAuthorizedException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.app.app_config.jwt_cookie_auth import (
    ACCESS_COOKIE_KEY,
    LEGACY_COOKIE_KEY,
    REFRESH_COOKIE_KEY,
    TokenSessionAuthenticationMiddleware,
    _decode_token,
    _encode_access_token,
    _encode_refresh_token,
    _issue_login_session,
    _revoke_family,
    _revoke_session_by_jti,
)
from convergence_games.db.models import Base, User, UserSession


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _create_user(session: AsyncSession) -> User:
    user = User(first_name="Test", last_name="User", over_18=True)
    session.add(user)
    await session.flush()
    return user


# --- helpers ---


@pytest.mark.asyncio
async def test_issue_login_session_creates_user_session_row(session: AsyncSession) -> None:
    user = await _create_user(session)
    access_cookie, refresh_cookie, jti = await _issue_login_session(
        session, user, [], user_agent="Test UA"
    )
    await session.flush()

    assert access_cookie.key == ACCESS_COOKIE_KEY
    assert refresh_cookie.key == REFRESH_COOKIE_KEY
    assert access_cookie.value
    assert refresh_cookie.value
    assert jti

    rows = (await session.execute(select(UserSession))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].jti == jti
    assert rows[0].family_id == jti  # fresh session: family == jti
    assert rows[0].user_agent == "Test UA"
    assert rows[0].revoked_at is None


@pytest.mark.asyncio
async def test_issue_login_session_uses_explicit_family_id(session: AsyncSession) -> None:
    user = await _create_user(session)
    _, _, original_jti = await _issue_login_session(session, user, [], user_agent=None)
    await session.flush()
    _, _, new_jti = await _issue_login_session(session, user, [], user_agent=None, family_id=original_jti)
    await session.flush()

    rows = (await session.execute(select(UserSession).order_by(UserSession.id))).scalars().all()
    assert len(rows) == 2
    assert rows[0].family_id == original_jti
    assert rows[1].family_id == original_jti
    assert rows[0].jti != rows[1].jti


@pytest.mark.asyncio
async def test_revoke_session_by_jti(session: AsyncSession) -> None:
    user = await _create_user(session)
    _, _, jti = await _issue_login_session(session, user, [], user_agent=None)
    await session.flush()

    await _revoke_session_by_jti(session, jti, reason="logout")
    await session.flush()

    row = (await session.execute(select(UserSession).where(UserSession.jti == jti))).scalar_one()
    assert row.revoked_at is not None
    assert row.revoked_reason == "logout"


@pytest.mark.asyncio
async def test_revoke_family_revokes_only_active(session: AsyncSession) -> None:
    user = await _create_user(session)
    _, _, j1 = await _issue_login_session(session, user, [], user_agent=None)
    await session.flush()
    _, _, j2 = await _issue_login_session(session, user, [], user_agent=None, family_id=j1)
    await session.flush()

    # Revoke first row up front (simulating a rotation)
    await _revoke_session_by_jti(session, j1, reason="rotated")
    await session.flush()

    await _revoke_family(session, j1, reason="reuse_detected")
    await session.flush()

    row1 = (await session.execute(select(UserSession).where(UserSession.jti == j1))).scalar_one()
    row2 = (await session.execute(select(UserSession).where(UserSession.jti == j2))).scalar_one()
    # Already-revoked row keeps its original reason; only previously-active rows in the family get
    # the new reason.
    assert row1.revoked_reason == "rotated"
    assert row2.revoked_reason == "reuse_detected"


# --- token encoding round-trip ---


@pytest.mark.asyncio
async def test_access_token_round_trip(session: AsyncSession) -> None:
    user = await _create_user(session)
    encoded, ttl = _encode_access_token(user, [])
    token = _decode_token(encoded)
    assert token.sub == str(user.id)
    assert token.token_type == "access"
    assert token.extras["first_name"] == "Test"
    assert token.extras["over_18"] is True
    assert ttl > dt.timedelta(0)


@pytest.mark.asyncio
async def test_refresh_token_round_trip() -> None:
    encoded, ttl = _encode_refresh_token(user_id=42, jti="my-test-jti")
    token = _decode_token(encoded)
    assert token.sub == "42"
    assert token.token_type == "refresh"
    assert token.jti == "my-test-jti"
    assert ttl > dt.timedelta(0)


def test_decode_token_invalid_raises() -> None:
    with pytest.raises(NotAuthorizedException):
        _decode_token("not-a-jwt")


# --- middleware: access path ---


def _make_connection(scope: dict[str, Any]) -> Any:
    """Build the minimum ASGI connection shape the middleware reads from."""
    from litestar.connection import ASGIConnection

    scope.setdefault("type", "http")
    scope.setdefault("headers", [])
    scope.setdefault("state", {})
    scope.setdefault("query_string", b"")
    scope.setdefault("path", "/")
    return ASGIConnection(scope)  # pyright: ignore[reportArgumentType]


def _scope_with_cookies(cookies: dict[str, str]) -> dict[str, Any]:
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header:
        headers.append((b"cookie", cookie_header.encode("ascii")))
    return {"type": "http", "headers": headers, "state": {}, "query_string": b"", "path": "/"}


def _make_middleware(engine: Any = None) -> TokenSessionAuthenticationMiddleware:
    """Construct middleware bypassing __init__ — we only call authenticate methods."""
    mw = TokenSessionAuthenticationMiddleware.__new__(TokenSessionAuthenticationMiddleware)
    mw.algorithm = "HS256"  # pyright: ignore[reportAttributeAccessIssue]
    mw.token_secret = ""  # pyright: ignore[reportAttributeAccessIssue]
    mw.token_cls = MagicMock()  # pyright: ignore[reportAttributeAccessIssue]
    return mw


@pytest.mark.asyncio
async def test_access_path_returns_user_from_claims() -> None:
    user = User(id=1, first_name="Alice", last_name="Smith", over_18=True)
    encoded, _ = _encode_access_token(user, [])
    scope = _scope_with_cookies({ACCESS_COOKIE_KEY: encoded})
    connection = _make_connection(scope)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)
    assert result.user is not None
    assert result.user.id == 1
    assert result.user.first_name == "Alice"


@pytest.mark.asyncio
async def test_no_cookies_returns_anonymous() -> None:
    scope = _scope_with_cookies({})
    connection = _make_connection(scope)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)
    assert result.user is None
    assert result.auth is None


@pytest.mark.asyncio
async def test_invalid_access_with_no_refresh_returns_anonymous() -> None:
    scope = _scope_with_cookies({ACCESS_COOKIE_KEY: "garbage"})
    connection = _make_connection(scope)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)
    assert result.user is None


# --- middleware: refresh path (via injected engine) ---


@pytest_asyncio.fixture
async def in_memory_engine(tmp_path: Any) -> AsyncGenerator[Any]:
    # File-backed SQLite so the multiple AsyncSessions opened by the middleware and the test
    # share the same DB (sqlite+aiosqlite:// would give each connection its own in-memory DB).
    db_path = tmp_path / "test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _connection_with_engine(scope: dict[str, Any], engine: Any) -> Any:
    from litestar.connection import ASGIConnection

    fake_app = MagicMock()
    fake_app.state.db_engine = engine
    scope.setdefault("type", "http")
    scope.setdefault("headers", [])
    scope.setdefault("state", {})
    scope.setdefault("query_string", b"")
    scope.setdefault("path", "/")
    # Litestar's ASGIConnection reads scope["litestar_app"] (and "app" as a fallback).
    scope["litestar_app"] = fake_app
    scope["app"] = fake_app
    return ASGIConnection(scope)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_refresh_path_rotates_and_authenticates(in_memory_engine: Any) -> None:
    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Bob", last_name="B", over_18=False)
            setup.add(user)
            await setup.flush()
            _, _, jti = await _issue_login_session(setup, user, [], user_agent=None)
            user_id = user.id

    refresh_token, _ = _encode_refresh_token(user_id, jti)
    scope = _scope_with_cookies({REFRESH_COOKIE_KEY: refresh_token})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)

    assert result.user is not None
    assert result.user.id == user_id

    # New cookies queued for the response.
    pending = scope["state"]["pending_auth_cookies"]
    pending_keys = {c.key for c in pending}
    assert ACCESS_COOKIE_KEY in pending_keys
    assert REFRESH_COOKIE_KEY in pending_keys

    # And the original session row is revoked with reason=rotated.
    async with factory() as verify:
        rows = (await verify.execute(select(UserSession).order_by(UserSession.id))).scalars().all()
        assert len(rows) == 2
        old, new = rows
        assert old.jti == jti
        assert old.revoked_reason == "rotated"
        assert new.revoked_at is None
        assert new.family_id == old.family_id


@pytest.mark.asyncio
async def test_refresh_path_reuse_detection_revokes_family(in_memory_engine: Any) -> None:
    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Carol", last_name="C", over_18=False)
            setup.add(user)
            await setup.flush()
            _, _, original_jti = await _issue_login_session(setup, user, [], user_agent=None)
            await setup.flush()
            # Simulate a rotation that happened a long time ago (outside the grace window).
            await _revoke_session_by_jti(setup, original_jti, reason="rotated")
            row = (await setup.execute(select(UserSession).where(UserSession.jti == original_jti))).scalar_one()
            row.revoked_at = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(minutes=10)
            # Active sibling (the rotated successor)
            _, _, new_jti = await _issue_login_session(
                setup, user, [], user_agent=None, family_id=original_jti
            )
            user_id = user.id

    # Replay the OLD jti — middleware should treat this as theft.
    replayed_token, _ = _encode_refresh_token(user_id, original_jti)
    scope = _scope_with_cookies({REFRESH_COOKIE_KEY: replayed_token})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)

    assert result.user is None  # unauthenticated

    async with factory() as verify:
        rows = (await verify.execute(select(UserSession).order_by(UserSession.id))).scalars().all()
        assert len(rows) == 2
        old = next(r for r in rows if r.jti == original_jti)
        new = next(r for r in rows if r.jti == new_jti)
        # Original row keeps its 'rotated' reason; the previously-active sibling is now revoked
        # with reason 'reuse_detected'.
        assert old.revoked_reason == "rotated"
        assert new.revoked_at is not None
        assert new.revoked_reason == "reuse_detected"


@pytest.mark.asyncio
async def test_refresh_path_grace_window_tolerates_rotated(in_memory_engine: Any) -> None:
    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Dan", last_name="D", over_18=False)
            setup.add(user)
            await setup.flush()
            _, _, original_jti = await _issue_login_session(setup, user, [], user_agent=None)
            await setup.flush()
            # Mark just-rotated (within grace window).
            await _revoke_session_by_jti(setup, original_jti, reason="rotated")
            await _issue_login_session(setup, user, [], user_agent=None, family_id=original_jti)
            user_id = user.id

    replayed_token, _ = _encode_refresh_token(user_id, original_jti)
    scope = _scope_with_cookies({REFRESH_COOKIE_KEY: replayed_token})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)

    # Inside the grace window the request is honoured — user is authenticated, no family-revoke.
    assert result.user is not None
    assert result.user.id == user_id

    async with factory() as verify:
        rows = (await verify.execute(select(UserSession))).scalars().all()
        # No row should have reason 'reuse_detected'.
        assert not any(r.revoked_reason == "reuse_detected" for r in rows)
        # Exactly one active sibling remains.
        active = [r for r in rows if r.revoked_at is None]
        assert len(active) == 1


# --- middleware: legacy migration ---


@pytest.mark.asyncio
async def test_legacy_cookie_migrates_and_clears(in_memory_engine: Any) -> None:
    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Eve", last_name="E", over_18=False)
            setup.add(user)
            await setup.flush()
            user_id = user.id

    # Build a legacy-shaped token: no token_type claim, current shape.
    from convergence_games.app.app_config.jwt_cookie_auth import _now
    from convergence_games.app.request_type import CustomToken
    from convergence_games.settings import SETTINGS

    legacy = CustomToken(
        sub=str(user_id),
        exp=_now() + dt.timedelta(days=30),
        extras={"first_name": "Eve", "last_name": "E", "over_18": False, "event_roles": []},
    )
    encoded = legacy.encode(secret=SETTINGS.TOKEN_SECRET, algorithm="HS256")

    scope = _scope_with_cookies({LEGACY_COOKIE_KEY: encoded})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)

    assert result.user is not None
    assert result.user.id == user_id

    pending = scope["state"]["pending_auth_cookies"]
    pending_keys = {c.key: c for c in pending}
    assert ACCESS_COOKIE_KEY in pending_keys
    assert REFRESH_COOKIE_KEY in pending_keys
    assert LEGACY_COOKIE_KEY in pending_keys
    # The legacy cookie is cleared.
    assert pending_keys[LEGACY_COOKIE_KEY].max_age == 0

    # And a user_session row was created.
    async with factory() as verify:
        rows = (await verify.execute(select(UserSession))).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == user_id
