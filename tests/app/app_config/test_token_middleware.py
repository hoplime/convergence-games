"""Tests for the JWTMultiCookieAuth + JWTMultiCookieAuthenticationMiddleware.

Covers cookie creation, the access hot path, refresh rotation with reuse detection
and grace window, legacy migration, and the DB helpers (create_user_session,
_revoke_session_by_jti, _revoke_family).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from litestar.connection import ASGIConnection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.app.app_config.jwt_cookie_auth import (
    _revoke_family,
    _revoke_session_by_jti,
    build_token_extras,
    create_user_session,
    jwt_cookie_auth,
)
from convergence_games.app.common.jwt_multi_cookie import (
    JWTMultiCookieAuthenticationMiddleware,
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


# --- DB helpers ---


@pytest.mark.asyncio
async def test_create_user_session_creates_row(session: AsyncSession) -> None:
    user = await _create_user(session)
    jti = "test-jti-1"
    await create_user_session(session, user.id, jti, user_agent="Test UA")
    await session.flush()

    rows = (await session.execute(select(UserSession))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].jti == jti
    assert rows[0].family_id == jti
    assert rows[0].user_agent == "Test UA"
    assert rows[0].revoked_at is None


@pytest.mark.asyncio
async def test_create_user_session_uses_explicit_family_id(session: AsyncSession) -> None:
    user = await _create_user(session)
    await create_user_session(session, user.id, "jti-1", user_agent=None)
    await session.flush()
    await create_user_session(session, user.id, "jti-2", user_agent=None, family_id="jti-1")
    await session.flush()

    rows = (await session.execute(select(UserSession).order_by(UserSession.id))).scalars().all()
    assert len(rows) == 2
    assert rows[0].family_id == "jti-1"
    assert rows[1].family_id == "jti-1"


@pytest.mark.asyncio
async def test_revoke_session_by_jti(session: AsyncSession) -> None:
    user = await _create_user(session)
    await create_user_session(session, user.id, "jti-revoke", user_agent=None)
    await session.flush()

    await _revoke_session_by_jti(session, "jti-revoke", reason="logout")
    await session.flush()

    row = (await session.execute(select(UserSession).where(UserSession.jti == "jti-revoke"))).scalar_one()
    assert row.revoked_at is not None
    assert row.revoked_reason == "logout"


@pytest.mark.asyncio
async def test_revoke_family_revokes_only_active(session: AsyncSession) -> None:
    user = await _create_user(session)
    await create_user_session(session, user.id, "fam-1", user_agent=None)
    await session.flush()
    await create_user_session(session, user.id, "fam-2", user_agent=None, family_id="fam-1")
    await session.flush()

    await _revoke_session_by_jti(session, "fam-1", reason="rotated")
    await session.flush()

    await _revoke_family(session, "fam-1", reason="reuse_detected")
    await session.flush()

    row1 = (await session.execute(select(UserSession).where(UserSession.jti == "fam-1"))).scalar_one()
    row2 = (await session.execute(select(UserSession).where(UserSession.jti == "fam-2"))).scalar_one()
    assert row1.revoked_reason == "rotated"
    assert row2.revoked_reason == "reuse_detected"


# --- JWTMultiCookieAuth cookie creation ---


def test_create_login_cookies_returns_three() -> None:
    cookies = jwt_cookie_auth.create_login_cookies(
        "42",
        token_extras={"first_name": "Test", "last_name": "User", "over_18": True, "event_roles": []},
        refresh_token_unique_jwt_id="my-jti",
    )
    assert len(cookies) == 3
    assert cookies[0].key == "access"
    assert cookies[1].key == "refresh"
    assert cookies[2].key == "token"
    assert cookies[2].max_age == 0


def test_create_refresh_cookie() -> None:
    cookie = jwt_cookie_auth.create_refresh_cookie("42", "test-jti")
    assert cookie.key == "refresh"
    assert cookie.value


def test_login_returns_response_with_cookies() -> None:
    response = jwt_cookie_auth.login(
        "42",
        token_extras={"first_name": "Test", "last_name": "User", "over_18": True, "event_roles": []},
        refresh_token_unique_jwt_id="my-jti",
    )
    cookie_keys = {c.key for c in response.cookies}
    assert "access" in cookie_keys
    assert "refresh" in cookie_keys
    assert "token" in cookie_keys


# --- Middleware tests ---


def _scope_with_cookies(cookies: dict[str, str]) -> dict[str, Any]:
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header:
        headers.append((b"cookie", cookie_header.encode("ascii")))
    return {"type": "http", "headers": headers, "state": {}, "query_string": b"", "path": "/"}


def _make_connection(scope: dict[str, Any]) -> Any:
    scope.setdefault("type", "http")
    scope.setdefault("headers", [])
    scope.setdefault("state", {})
    scope.setdefault("query_string", b"")
    scope.setdefault("path", "/")
    return ASGIConnection(scope)  # pyright: ignore[reportArgumentType]


def _make_middleware() -> JWTMultiCookieAuthenticationMiddleware:
    from convergence_games.app.request_type import CustomToken
    from convergence_games.settings import SETTINGS

    mw = JWTMultiCookieAuthenticationMiddleware.__new__(JWTMultiCookieAuthenticationMiddleware)
    mw.algorithm = "HS256"
    mw.token_secret = SETTINGS.TOKEN_SECRET
    mw.token_cls = CustomToken
    mw.auth_cookie_key = "access"
    mw.refresh_cookie_key = "refresh"
    mw.legacy_cookie_key = "token"
    mw.refresh_handler = None
    mw.legacy_handler = None
    mw.rotation_grace_seconds = 5
    mw.access_token_expiration = dt.timedelta(minutes=15)
    mw.cookie_path = "/"
    mw.cookie_secure = None
    mw.cookie_samesite = "lax"
    mw.cookie_domain = None
    mw.retrieve_user_handler = MagicMock()  # type: ignore
    return mw


def _connection_with_engine(scope: dict[str, Any], engine: Any) -> Any:
    fake_app = MagicMock()
    fake_app.state.db_engine = engine
    scope.setdefault("type", "http")
    scope.setdefault("headers", [])
    scope.setdefault("state", {})
    scope.setdefault("query_string", b"")
    scope.setdefault("path", "/")
    scope["litestar_app"] = fake_app
    scope["app"] = fake_app
    return ASGIConnection(scope)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_access_path_returns_user_from_claims() -> None:
    from convergence_games.app.app_config.jwt_cookie_auth import retrieve_user_handler

    user = User(id=1, first_name="Alice", last_name="Smith", over_18=True)
    cookies = jwt_cookie_auth.create_login_cookies("1", token_extras=build_token_extras(user, []))
    access_cookie = cookies[0]
    assert access_cookie.value is not None

    scope = _scope_with_cookies({"access": access_cookie.value})
    connection = _make_connection(scope)
    mw = _make_middleware()
    mw.retrieve_user_handler = retrieve_user_handler  # type: ignore
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
    scope = _scope_with_cookies({"access": "garbage"})
    connection = _make_connection(scope)
    mw = _make_middleware()
    result = await mw.authenticate_request(connection)
    assert result.user is None


# --- Refresh/legacy path tests (file-backed SQLite) ---


@pytest_asyncio.fixture
async def in_memory_engine(tmp_path: Any) -> AsyncGenerator[Any]:
    db_path = tmp_path / "test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_path_rotates_and_authenticates(in_memory_engine: Any) -> None:
    from convergence_games.app.app_config.jwt_cookie_auth import _handle_refresh

    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Bob", last_name="B", over_18=False)
            setup.add(user)
            await setup.flush()
            jti = "bob-jti"
            await create_user_session(setup, user.id, jti, user_agent=None)
            user_id = user.id

    refresh_cookie = jwt_cookie_auth.create_refresh_cookie(str(user_id), jti)
    assert refresh_cookie.value is not None
    scope = _scope_with_cookies({"refresh": refresh_cookie.value})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    mw.refresh_handler = _handle_refresh
    result = await mw.authenticate_request(connection)

    assert result.user is not None
    assert result.user.id == user_id

    pending = scope["state"]["pending_auth_cookies"]
    pending_keys = {c.key for c in pending}
    assert "access" in pending_keys
    assert "refresh" in pending_keys

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
    from convergence_games.app.app_config.jwt_cookie_auth import _handle_refresh

    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Carol", last_name="C", over_18=False)
            setup.add(user)
            await setup.flush()
            original_jti = "carol-jti-1"
            await create_user_session(setup, user.id, original_jti, user_agent=None)
            await setup.flush()
            await _revoke_session_by_jti(setup, original_jti, reason="rotated")
            row = (await setup.execute(select(UserSession).where(UserSession.jti == original_jti))).scalar_one()
            row.revoked_at = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(minutes=10)
            new_jti = "carol-jti-2"
            await create_user_session(setup, user.id, new_jti, user_agent=None, family_id=original_jti)
            user_id = user.id

    replayed_cookie = jwt_cookie_auth.create_refresh_cookie(str(user_id), original_jti)
    assert replayed_cookie.value is not None
    scope = _scope_with_cookies({"refresh": replayed_cookie.value})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    mw.refresh_handler = _handle_refresh
    result = await mw.authenticate_request(connection)

    assert result.user is None

    async with factory() as verify:
        rows = (await verify.execute(select(UserSession).order_by(UserSession.id))).scalars().all()
        assert len(rows) == 2
        old = next(r for r in rows if r.jti == original_jti)
        new = next(r for r in rows if r.jti == new_jti)
        assert old.revoked_reason == "rotated"
        assert new.revoked_at is not None
        assert new.revoked_reason == "reuse_detected"


@pytest.mark.asyncio
async def test_refresh_path_grace_window_tolerates_rotated(in_memory_engine: Any) -> None:
    from convergence_games.app.app_config.jwt_cookie_auth import _handle_refresh

    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Dan", last_name="D", over_18=False)
            setup.add(user)
            await setup.flush()
            original_jti = "dan-jti-1"
            await create_user_session(setup, user.id, original_jti, user_agent=None)
            await setup.flush()
            await _revoke_session_by_jti(setup, original_jti, reason="rotated")
            await create_user_session(setup, user.id, "dan-jti-2", user_agent=None, family_id=original_jti)
            user_id = user.id

    replayed_cookie = jwt_cookie_auth.create_refresh_cookie(str(user_id), original_jti)
    assert replayed_cookie.value is not None
    scope = _scope_with_cookies({"refresh": replayed_cookie.value})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    mw.refresh_handler = _handle_refresh
    result = await mw.authenticate_request(connection)

    assert result.user is not None
    assert result.user.id == user_id

    async with factory() as verify:
        rows = (await verify.execute(select(UserSession))).scalars().all()
        assert not any(r.revoked_reason == "reuse_detected" for r in rows)
        active = [r for r in rows if r.revoked_at is None]
        assert len(active) == 1


@pytest.mark.asyncio
async def test_legacy_cookie_migrates_and_clears(in_memory_engine: Any) -> None:
    from convergence_games.app.app_config.jwt_cookie_auth import _handle_legacy

    factory = async_sessionmaker(in_memory_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        async with setup.begin():
            user = User(first_name="Eve", last_name="E", over_18=False)
            setup.add(user)
            await setup.flush()
            user_id = user.id

    from convergence_games.app.request_type import CustomToken
    from convergence_games.settings import SETTINGS

    legacy = CustomToken(
        sub=str(user_id),
        exp=dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(days=30),
        extras={"first_name": "Eve", "last_name": "E", "over_18": False, "event_roles": []},
    )
    encoded = legacy.encode(secret=SETTINGS.TOKEN_SECRET, algorithm="HS256")

    scope = _scope_with_cookies({"token": encoded})
    connection = _connection_with_engine(scope, in_memory_engine)
    mw = _make_middleware()
    mw.legacy_handler = _handle_legacy
    result = await mw.authenticate_request(connection)

    assert result.user is not None
    assert result.user.id == user_id

    pending = scope["state"]["pending_auth_cookies"]
    pending_keys = {c.key: c for c in pending}
    assert "access" in pending_keys
    assert "refresh" in pending_keys
    assert "token" in pending_keys
    assert pending_keys["token"].max_age == 0

    async with factory() as verify:
        rows = (await verify.execute(select(UserSession))).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == user_id
