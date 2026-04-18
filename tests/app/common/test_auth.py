"""Tests for authorize_flow intent matrix and find_user_by_email."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.app.common.auth import (
    AccountAlreadyExistsError,
    AuthIntent,
    NoAccountForSignInError,
    ProfileInfo,
    authorize_flow,
    find_user_by_email,
)
from convergence_games.db.enums import LoginProvider
from convergence_games.db.models import Base, User, UserLogin


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _create_user_with_login(
    session: AsyncSession,
    provider: LoginProvider,
    provider_user_id: str,
    provider_email: str | None = None,
    first_name: str = "Test",
) -> User:
    user = User(
        first_name=first_name,
        last_name="User",
        logins=[
            UserLogin(
                provider=provider,
                provider_user_id=provider_user_id,
                provider_email=provider_email,
            )
        ],
    )
    session.add(user)
    await session.flush()
    return user


# --- find_user_by_email ---


@pytest.mark.asyncio
async def test_find_user_by_email_returns_none_when_no_match(session: AsyncSession) -> None:
    result = await find_user_by_email(session, "nobody@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_find_user_by_email_matches_provider_email(session: AsyncSession) -> None:
    user = await _create_user_with_login(
        session, LoginProvider.GOOGLE, "google-sub-123", provider_email="alice@example.com"
    )
    found = await find_user_by_email(session, "alice@example.com")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_find_user_by_email_matches_email_provider_user_id(session: AsyncSession) -> None:
    user = await _create_user_with_login(
        session, LoginProvider.EMAIL, "bob@example.com", provider_email="bob@example.com"
    )
    found = await find_user_by_email(session, "bob@example.com")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_find_user_by_email_case_insensitive(session: AsyncSession) -> None:
    user = await _create_user_with_login(
        session, LoginProvider.EMAIL, "carol@example.com", provider_email="Carol@Example.COM"
    )
    found = await find_user_by_email(session, "CAROL@EXAMPLE.COM")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_find_user_by_email_prefers_email_provider(session: AsyncSession) -> None:
    email_user = await _create_user_with_login(
        session, LoginProvider.EMAIL, "shared@example.com", provider_email="shared@example.com",
        first_name="EmailUser",
    )
    _ = await _create_user_with_login(
        session, LoginProvider.GOOGLE, "google-sub-456", provider_email="shared@example.com",
        first_name="GoogleUser",
    )
    found = await find_user_by_email(session, "shared@example.com")
    assert found is not None
    assert found.id == email_user.id


# --- authorize_flow: SIGN_UP ---


@pytest.mark.asyncio
async def test_sign_up_creates_user(session: AsyncSession) -> None:
    profile = ProfileInfo(user_id="new@example.com", user_email="new@example.com")
    redirect = await authorize_flow(
        transaction=session,
        provider_name=LoginProvider.EMAIL,
        profile_info=profile,
        intent=AuthIntent.SIGN_UP,
    )
    assert redirect.status_code in (301, 302, 303, 307)


@pytest.mark.asyncio
async def test_sign_up_raises_on_duplicate(session: AsyncSession) -> None:
    _ = await _create_user_with_login(session, LoginProvider.EMAIL, "dup@example.com")
    profile = ProfileInfo(user_id="dup@example.com", user_email="dup@example.com")
    with pytest.raises(AccountAlreadyExistsError):
        _ = await authorize_flow(
            transaction=session,
            provider_name=LoginProvider.EMAIL,
            profile_info=profile,
            intent=AuthIntent.SIGN_UP,
        )


# --- authorize_flow: SIGN_IN ---


@pytest.mark.asyncio
async def test_sign_in_succeeds_for_existing_user(session: AsyncSession) -> None:
    _ = await _create_user_with_login(
        session, LoginProvider.EMAIL, "existing@example.com", provider_email="existing@example.com"
    )
    profile = ProfileInfo(user_id="existing@example.com", user_email="existing@example.com")
    redirect = await authorize_flow(
        transaction=session,
        provider_name=LoginProvider.EMAIL,
        profile_info=profile,
        intent=AuthIntent.SIGN_IN,
    )
    assert redirect.status_code in (301, 302, 303, 307)


@pytest.mark.asyncio
async def test_sign_in_raises_on_miss(session: AsyncSession) -> None:
    profile = ProfileInfo(user_id="ghost@example.com", user_email="ghost@example.com")
    with pytest.raises(NoAccountForSignInError):
        _ = await authorize_flow(
            transaction=session,
            provider_name=LoginProvider.EMAIL,
            profile_info=profile,
            intent=AuthIntent.SIGN_IN,
        )


# --- authorize_flow: LINK ---


@pytest.mark.asyncio
async def test_link_attaches_new_login(session: AsyncSession) -> None:
    user = await _create_user_with_login(
        session, LoginProvider.EMAIL, "linker@example.com", provider_email="linker@example.com"
    )
    profile = ProfileInfo(user_id="google-sub-789", user_email="linker@example.com")
    redirect = await authorize_flow(
        transaction=session,
        provider_name=LoginProvider.GOOGLE,
        profile_info=profile,
        intent=AuthIntent.LINK,
        linking_account_id=user.id,
    )
    assert redirect.status_code in (301, 302, 303, 307)


@pytest.mark.asyncio
async def test_link_idempotent_same_user(session: AsyncSession) -> None:
    user = await _create_user_with_login(
        session, LoginProvider.GOOGLE, "google-sub-same", provider_email="same@example.com"
    )
    profile = ProfileInfo(user_id="google-sub-same", user_email="same@example.com")
    _ = await authorize_flow(
        transaction=session,
        provider_name=LoginProvider.GOOGLE,
        profile_info=profile,
        intent=AuthIntent.LINK,
        linking_account_id=user.id,
    )


@pytest.mark.asyncio
async def test_link_rejects_cross_user(session: AsyncSession) -> None:
    _user_a = await _create_user_with_login(
        session, LoginProvider.GOOGLE, "google-sub-a", provider_email="a@example.com", first_name="A"
    )
    user_b = await _create_user_with_login(
        session, LoginProvider.EMAIL, "b@example.com", provider_email="b@example.com", first_name="B"
    )
    profile = ProfileInfo(user_id="google-sub-a", user_email="a@example.com")
    from litestar.exceptions import HTTPException

    with pytest.raises(HTTPException, match="403"):
        _ = await authorize_flow(
            transaction=session,
            provider_name=LoginProvider.GOOGLE,
            profile_info=profile,
            intent=AuthIntent.LINK,
            linking_account_id=user_b.id,
        )
